"""Phase 3.2 daily digest — bundle yesterday's summaries into one email.

`send_daily_digest()` is the single entry point. It:

1. Pulls every `conversation_summaries` row with `created_at` in the
   last `digest_window_hours` (default 24).
2. Groups by chat_jid, formats one card per thread plus a top-of-mail
   "open action items" list aggregating every unticked task.
3. Sends via Resend to `settings.broker_email`. Graceful no-op when
   either Resend or the recipient is unconfigured — caller sees a
   reason string and decides what to log.

Designed to run from `POST /whatsapp/summaries/send-digest` (manual
trigger from the admin UI) and from a future Cloud Scheduler cron
firing at 08:00 Jerusalem.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.config import settings
from shmuel_backend.email_client import send_email
from shmuel_backend.models import ConversationSummary

log = logging.getLogger(__name__)


@dataclass
class DigestResult:
    """Caller-visible outcome of a single digest attempt."""

    sent: bool = False
    reason: str | None = None
    summaries_included: int = 0
    threads_included: int = 0
    recipient: str | None = None


def _jerusalem_today_label(now: datetime) -> str:
    """Human-readable date label in the subject line (Jerusalem time)."""
    local = now.astimezone(ZoneInfo("Asia/Jerusalem"))
    return local.strftime("%a %b %d")


def _format_card_html(label: str, s: ConversationSummary) -> str:
    """One thread's summary as a styled HTML card.

    Inline styles only — most email clients strip <style>. Mirrors the
    visual language of the existing newsletter digest emails (Lato
    body, golden accents).
    """
    actions = (
        "<ul style='margin:6px 0 0;padding-left:20px;'>"
        + "".join(f"<li>{escape(a)}</li>" for a in s.action_items)
        + "</ul>"
        if s.action_items
        else ""
    )
    pills = []
    for a in s.mentioned_amounts:
        pills.append(
            "<span style='background:#fef3c7;color:#92400e;font-size:11px;"
            "padding:2px 8px;border-radius:999px;margin-right:4px;'>"
            f"{escape(a)}</span>"
        )
    for d in s.mentioned_dates:
        pills.append(
            "<span style='background:#dbeafe;color:#1e40af;font-size:11px;"
            "padding:2px 8px;border-radius:999px;margin-right:4px;'>"
            f"{escape(d)}</span>"
        )
    pills_html = (
        f"<div style='margin-top:8px'>{''.join(pills)}</div>" if pills else ""
    )
    return (
        "<div style='border:1px solid #ece4d2;border-radius:8px;"
        "padding:14px 18px;margin-bottom:12px;background:#fff;'>"
        f"<div style='font-weight:600;margin-bottom:4px'>{escape(label)}</div>"
        f"<div style='color:#444;line-height:1.5'>{escape(s.summary)}</div>"
        f"{actions}{pills_html}"
        "</div>"
    )


def _format_card_text(label: str, s: ConversationSummary) -> str:
    """Plain-text fallback for the same card. Keeps spam-score down
    by giving non-HTML clients a real body, not a 'see HTML version'
    placeholder."""
    lines = [f"=== {label} ===", s.summary]
    if s.action_items:
        lines.append("Action items:")
        lines.extend(f"  - {a}" for a in s.action_items)
    if s.mentioned_amounts:
        lines.append("Amounts: " + ", ".join(s.mentioned_amounts))
    if s.mentioned_dates:
        lines.append("Dates: " + ", ".join(s.mentioned_dates))
    return "\n".join(lines)


def _thread_label(s: ConversationSummary) -> str:
    """Short identifier shown in the card header — phone over JID."""
    return f"+{s.phone_number}" if s.phone_number else s.chat_jid


def _build_digest_bodies(
    summaries: list[ConversationSummary], *, window_label: str
) -> tuple[str, str, str]:
    """Compose (subject, html_body, text_body) for the email.

    Groups summaries by chat_jid so a chatty thread with multiple
    period rows in the window collapses to one card (most recent
    summary wins, with all action items aggregated)."""
    by_thread: dict[str, list[ConversationSummary]] = {}
    for s in summaries:
        by_thread.setdefault(s.chat_jid, []).append(s)

    # Per thread, pick the latest period_end as the "representative"
    # card; concatenate action items in chronological order so older
    # uncompleted asks stay visible.
    cards_html: list[str] = []
    cards_text: list[str] = []
    all_actions: list[tuple[str, str]] = []  # (label, action)
    for jid, rows in by_thread.items():
        rows_sorted = sorted(rows, key=lambda r: r.period_end)
        latest = rows_sorted[-1]
        label = _thread_label(latest)
        # Aggregate action items across all period rows in the window.
        agg_actions: list[str] = []
        for r in rows_sorted:
            agg_actions.extend(r.action_items)
        # Build a synthetic row that carries aggregated actions so the
        # card renderer surfaces them all.
        agg = ConversationSummary(
            id=latest.id,
            chat_jid=jid,
            phone_number=latest.phone_number,
            contact_id=latest.contact_id,
            period_start=latest.period_start,
            period_end=latest.period_end,
            message_count=sum(r.message_count for r in rows_sorted),
            summary=latest.summary,
            action_items=agg_actions,
            mentioned_amounts=latest.mentioned_amounts,
            mentioned_dates=latest.mentioned_dates,
        )
        cards_html.append(_format_card_html(label, agg))
        cards_text.append(_format_card_text(label, agg))
        all_actions.extend((label, a) for a in agg_actions)

    actions_html = ""
    actions_text = ""
    if all_actions:
        items = "".join(
            f"<li><strong>{escape(label)}:</strong> {escape(a)}</li>"
            for label, a in all_actions
        )
        actions_html = (
            "<h2 style='margin:0 0 8px;font-size:18px;color:#1f2937;'>"
            "Open action items</h2>"
            f"<ul style='margin:0 0 24px;padding-left:20px;line-height:1.6'>{items}</ul>"
        )
        actions_text = "Open action items:\n" + "\n".join(
            f"  - [{label}] {a}" for label, a in all_actions
        ) + "\n\n"

    subject = (
        f"Daily WhatsApp digest — {window_label} "
        f"({len(by_thread)} thread{'s' if len(by_thread) != 1 else ''})"
    )
    html = (
        "<div style='font-family:Lato,Arial,sans-serif;max-width:640px;"
        "margin:0 auto;padding:20px;background:#faf6ef;'>"
        f"<h1 style='font-size:22px;color:#1f2937;margin:0 0 6px'>"
        f"Daily WhatsApp digest</h1>"
        f"<p style='color:#6b7280;margin:0 0 18px'>{escape(window_label)}</p>"
        f"{actions_html}"
        f"<h2 style='margin:0 0 8px;font-size:18px;color:#1f2937;'>"
        f"Threads</h2>"
        f"{''.join(cards_html)}"
        "</div>"
    )
    text = (
        f"Daily WhatsApp digest — {window_label}\n\n"
        f"{actions_text}"
        f"Threads:\n\n" + "\n\n".join(cards_text)
    )
    return subject, html, text


async def send_daily_digest(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> DigestResult:
    """Build and send the digest. Returns what happened.

    Skip reasons:
    - `no_recipient` — `settings.broker_email` unset
    - `no_summaries` — nothing landed in the window (don't spam empties)
    - `resend_failed` — Resend rejected; check email_client logs
    - `resend_no_op` — Resend key unset (dev/CI default)
    """
    now = now or datetime.now(UTC)
    recipient = settings.broker_email.strip()
    result = DigestResult(recipient=recipient or None)
    if not recipient:
        result.reason = "no_recipient"
        return result

    window_start = (now - timedelta(hours=settings.digest_window_hours)).replace(
        tzinfo=None
    )
    rows = await session.execute(
        select(ConversationSummary)
        .where(ConversationSummary.created_at >= window_start)
        .order_by(ConversationSummary.created_at.asc())
    )
    summaries = list(rows.scalars().all())
    if not summaries:
        result.reason = "no_summaries"
        return result

    result.summaries_included = len(summaries)
    result.threads_included = len({s.chat_jid for s in summaries})

    subject, html, text = _build_digest_bodies(
        summaries,
        window_label=_jerusalem_today_label(now),
    )
    sent = await send_email(
        to=recipient,
        subject=subject,
        html=html,
        text=text,
    )
    if not sent:
        # send_email returns False both when Resend is unconfigured and
        # when a real send failed — distinguish for the caller.
        result.reason = (
            "resend_no_op" if not settings.resend_api_key else "resend_failed"
        )
        return result
    result.sent = True
    return result
