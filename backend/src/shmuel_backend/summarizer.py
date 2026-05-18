"""Phase 3.2 — summarize WhatsApp threads into CRM-attached notes.

For each thread with new messages since its previous summary, this
module:

1. Pulls the messages in the current period (since the last summary's
   period_end, or the thread's first message if none yet).
2. Calls the LLM (structured output) to produce a summary paragraph
   plus extracted action items, mentioned dates, and mentioned amounts.
3. Resolves the contact by phone-match against `contacts`.
4. Writes a `conversation_summaries` row keyed on (chat_jid,
   period_end) so re-running for the same window updates instead of
   duplicating.

Degrades gracefully: missing `openai_api_key` means we skip the
summary call but still record what messages were considered, so
re-runs are idempotent without spuriously creating empty rows. The
function returns a `SummarizeRun` describing what it did so the admin
UI / cron logs can see attempts vs successes.

Designed to be called on demand (admin button) and from a future
Cloud Scheduler cron. No persistent background worker required.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.chatbot import normalize_phone, phone_from_jid
from shmuel_backend.config import settings
from shmuel_backend.models import (
    Contact,
    ConversationSummary,
    WhatsappMessage,
    WhatsappThread,
)

log = logging.getLogger(__name__)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

SUMMARIZE_SYSTEM_PROMPT = (
    "You summarize WhatsApp conversations between a Jerusalem real-estate "
    "broker and a lead. Output ONLY valid JSON matching this schema:\n"
    '{"summary": string,\n'
    ' "action_items": [string, ...],\n'
    ' "mentioned_amounts": [string, ...],\n'
    ' "mentioned_dates": [string, ...]}\n\n'
    "Rules:\n"
    "- summary: 1-3 sentence paragraph, factual, third-person. Avoid "
    "  filler. Note the lead's stated criteria and any commitments made.\n"
    "- action_items: short imperative bullets for the broker (e.g.\n"
    "  'call back Tuesday about Talbiya 3BR'). Empty array if none.\n"
    "- mentioned_amounts: any price/budget figures the lead said, in "
    "  their original wording.\n"
    "- mentioned_dates: any dates / move-in / viewing times the lead "
    "  said, in their original wording.\n"
    "- Echo amounts and dates verbatim; do not normalize."
)


@dataclass
class ThreadSummaryResult:
    """Per-thread outcome of one summarization pass."""

    thread_id: str
    chat_jid: str
    message_count: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    summary_id: str | None = None
    skipped_reason: str | None = None


@dataclass
class SummarizeRun:
    """Aggregate run result. The router returns this directly."""

    attempted: int = 0
    summarized: int = 0
    skipped: int = 0
    threads: list[ThreadSummaryResult] = field(default_factory=list)


def _to_naive_utc(dt: datetime) -> datetime:
    """Strip tzinfo (convert to UTC first) so we can store and compare
    against the schema's naive `DateTime` columns."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


async def _previous_period_end(
    session: AsyncSession, chat_jid: str
) -> datetime | None:
    """The end of the most recent summary window for this thread, or
    None if no prior summary exists (then we'll start from the
    thread's first message)."""
    rows = await session.execute(
        select(ConversationSummary.period_end)
        .where(ConversationSummary.chat_jid == chat_jid)
        .order_by(desc(ConversationSummary.period_end))
        .limit(1)
    )
    return rows.scalar_one_or_none()


async def _fetch_period_messages(
    session: AsyncSession,
    *,
    chat_jid: str,
    after: datetime | None,
    until: datetime,
) -> list[WhatsappMessage]:
    """All messages in (after, until]. Sorted oldest first so the LLM
    sees the conversation chronologically."""
    stmt = select(WhatsappMessage).where(
        WhatsappMessage.chat_jid == chat_jid,
        WhatsappMessage.created_at <= until,
    )
    if after is not None:
        stmt = stmt.where(WhatsappMessage.created_at > after)
    stmt = stmt.order_by(WhatsappMessage.created_at.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


def _format_messages_for_prompt(
    messages: list[WhatsappMessage],
) -> str:
    """Compact 'time | from | text' lines for the LLM."""
    lines: list[str] = []
    for m in messages:
        ts = m.created_at.isoformat() if m.created_at else "?"
        who = m.from_name or m.from_phone or "lead"
        body = (m.text or f"({m.media_type or 'no text'})").strip()
        lines.append(f"{ts} | {who} | {body}")
    return "\n".join(lines)


async def call_openai_summarize(transcript: str) -> dict[str, Any] | None:
    """Hit OpenAI for the structured summary. None on any failure path."""
    if not settings.openai_api_key:
        log.info(
            "summarizer: OpenAI key unset; would have summarized %d chars",
            len(transcript),
        )
        return None
    payload = {
        "model": settings.openai_chat_model,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(OPENAI_ENDPOINT, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.warning("summarizer: openai %s: %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("summarizer: openai request failed: %s", exc)
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        log.warning("summarizer: bad JSON: %s", content[:200])
        return None


async def _resolve_contact_id(
    session: AsyncSession, phone: str | None
) -> Any | None:
    """Best-effort phone→contact match. Empty/missing phone → None."""
    if not phone:
        return None
    row = await session.execute(
        select(Contact.id).where(Contact.phone == phone).limit(1)
    )
    return row.scalar_one_or_none()


def _list_or_empty(value: Any) -> list[str]:
    """Defensive cast — LLM occasionally returns null where we want []."""
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    return []


async def summarize_thread(
    session: AsyncSession,
    thread: WhatsappThread,
    *,
    until: datetime | None = None,
) -> ThreadSummaryResult:
    """Summarize one thread's new messages.

    Idempotent on (chat_jid, period_end). If `until` falls within an
    existing summary window, that row is updated in place.
    """
    result = ThreadSummaryResult(
        thread_id=str(thread.id),
        chat_jid=thread.chat_jid,
    )
    period_end = _to_naive_utc(until or datetime.now(UTC))
    after = await _previous_period_end(session, thread.chat_jid)
    if after is not None and after >= period_end:
        result.skipped_reason = "already_summarized"
        return result

    messages = await _fetch_period_messages(
        session,
        chat_jid=thread.chat_jid,
        after=after,
        until=period_end,
    )
    if not messages:
        result.skipped_reason = "no_new_messages"
        return result

    result.message_count = len(messages)
    result.period_start = after or messages[0].created_at
    result.period_end = period_end

    transcript = _format_messages_for_prompt(messages)
    parsed = await call_openai_summarize(transcript)
    if parsed is None:
        # No LLM — skip writing rather than fabricate. Re-runnable next
        # time the key is set.
        result.skipped_reason = "llm_unavailable"
        return result

    summary = (parsed.get("summary") or "").strip()
    if not summary:
        result.skipped_reason = "empty_summary"
        return result

    contact_id = await _resolve_contact_id(
        session, thread.phone_number or phone_from_jid(thread.chat_jid)
    )

    bind = session.get_bind() if session.bind is None else session.bind
    dialect = bind.dialect.name if bind is not None else "postgresql"

    values = {
        "chat_jid": thread.chat_jid,
        "phone_number": normalize_phone(thread.phone_number),
        "contact_id": contact_id,
        "period_start": result.period_start,
        "period_end": result.period_end,
        "message_count": result.message_count,
        "summary": summary,
        "action_items": _list_or_empty(parsed.get("action_items")),
        "mentioned_amounts": _list_or_empty(parsed.get("mentioned_amounts")),
        "mentioned_dates": _list_or_empty(parsed.get("mentioned_dates")),
    }

    if dialect == "postgresql":
        stmt = (
            pg_insert(ConversationSummary)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_conversation_summaries_period",
                set_={
                    "summary": values["summary"],
                    "action_items": values["action_items"],
                    "mentioned_amounts": values["mentioned_amounts"],
                    "mentioned_dates": values["mentioned_dates"],
                    "message_count": values["message_count"],
                    "period_start": values["period_start"],
                    "contact_id": values["contact_id"],
                },
            )
            .returning(ConversationSummary.id)
        )
        ret = await session.execute(stmt)
        summary_id = ret.scalar_one()
    else:
        existing = await session.execute(
            select(ConversationSummary).where(
                ConversationSummary.chat_jid == values["chat_jid"],
                ConversationSummary.period_end == values["period_end"],
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            for k in (
                "summary",
                "action_items",
                "mentioned_amounts",
                "mentioned_dates",
                "message_count",
                "period_start",
                "contact_id",
            ):
                setattr(row, k, values[k])
            summary_id = row.id
        else:
            new = ConversationSummary(**values)
            session.add(new)
            await session.flush()
            summary_id = new.id

    await session.commit()
    result.summary_id = str(summary_id)
    return result


async def summarize_all_threads(
    session: AsyncSession,
    *,
    until: datetime | None = None,
    only_threads_active_within: timedelta = timedelta(days=2),
) -> SummarizeRun:
    """Walk every thread with recent activity and summarize new
    messages on each. Skips silent threads to keep the run cheap.

    `only_threads_active_within` is the freshness window — threads
    with no message in this long aren't worth re-checking. Default 2
    days handles "the cron ran yesterday and we want to catch
    anything that came in late."
    """
    until = until or datetime.now(UTC)
    activity_floor = _to_naive_utc(until - only_threads_active_within)
    rows = await session.execute(
        select(WhatsappThread).where(
            WhatsappThread.last_message_at >= activity_floor
        )
    )
    threads = list(rows.scalars().all())

    run = SummarizeRun()
    for t in threads:
        run.attempted += 1
        outcome = await summarize_thread(session, t, until=until)
        run.threads.append(outcome)
        if outcome.summary_id is not None:
            run.summarized += 1
        else:
            run.skipped += 1
    log.info(
        "summarizer: attempted=%d summarized=%d skipped=%d",
        run.attempted, run.summarized, run.skipped,
    )
    return run
