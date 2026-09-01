"""Pull a structured lead out of a conversation, for Shmuel to approve.

The summarizer already turns a WhatsApp thread into a paragraph plus action
items. That is useful for reading, but not for the address book: it does not
say "3 bedrooms, City Center, unfurnished, needs parking, family of six".
This module extracts exactly that.

Deliberately a review queue, not a write-through. Extraction from a text
thread is decent; extraction from a phone transcript that code-switches
between Hebrew and English is not, and a wrong contact is harder to spot
later than a missing one. Every extraction lands as PENDING and becomes a
Contact only when approved from the admin.

Written so a call transcript and a WhatsApp thread go through the same path —
the only difference is `source` and what text gets passed in.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select

from shmuel_backend.config import settings
from shmuel_backend.enums import LeadSource, LeadStatus
from shmuel_backend.models import Contact, LeadExtraction

log = logging.getLogger(__name__)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

EXTRACT_SYSTEM_PROMPT = (
    "You read a conversation between a Jerusalem real-estate broker and a "
    "prospective client, and extract what the client is looking for. The "
    "conversation may mix Hebrew and English, and may be a phone transcript "
    "with transcription errors. Output ONLY valid JSON matching this "
    "schema:\n"
    '{"display_name": string|null,\n'
    ' "summary": string,\n'
    ' "requirements": {\n'
    '   "deal_type": "rent"|"buy"|null,\n'
    '   "rooms": string|null,\n'
    '   "neighborhoods": [string, ...],\n'
    '   "furnished": "furnished"|"unfurnished"|null,\n'
    '   "parking": true|false|null,\n'
    '   "household": string|null,\n'
    '   "timing": string|null,\n'
    '   "budget": string|null,\n'
    '   "other": [string, ...]\n'
    " }}\n\n"
    "Rules:\n"
    "- Extract ONLY what the client actually said. Never infer, never fill a "
    "  field to seem complete. Unknown means null, or an empty array.\n"
    "- summary: 1-2 factual sentences a broker can act on.\n"
    "- rooms/household/timing/budget: keep the client's own wording "
    "  ('3 bedrooms', 'family of 6', 'asap', 'up to 9000 a month').\n"
    "- neighborhoods: Jerusalem neighbourhood names only, as said.\n"
    "- parking: true only if they asked for it, false only if they said they "
    "  do not need it, otherwise null.\n"
    "- other: any further requirement that does not fit a field above "
    "  (e.g. 'ground floor', 'shabbat elevator', 'balcony').\n"
    "- If the conversation contains no property requirement at all, return "
    '  summary as "" and leave every requirement null/empty.'
)

REQUIREMENT_KEYS = (
    "deal_type",
    "rooms",
    "neighborhoods",
    "furnished",
    "parking",
    "household",
    "timing",
    "budget",
    "other",
)


async def _call_llm(transcript: str) -> dict[str, Any] | None:
    """Ask the model for the structured lead. None on any failure path.

    Mirrors summarizer._summarize_via_llm rather than sharing it: the two
    have different prompts and different failure logging, and coupling them
    would mean one prompt change risking the other feature.
    """
    if not settings.openai_api_key:
        log.info("lead_extraction: OpenAI key unset; skipping extraction")
        return None
    payload = {
        "model": settings.openai_chat_model,
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
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
            log.warning(
                "lead_extraction: openai %s: %s", resp.status_code, resp.text[:300]
            )
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("lead_extraction: openai request failed: %s", exc)
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        log.warning("lead_extraction: bad JSON: %s", content[:200])
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean_requirements(raw: Any) -> dict[str, Any]:
    """Keep only known keys, drop nulls and empties.

    The model is told to use null for unknowns; storing those would make an
    empty extraction look like a rich one in the admin.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in REQUIREMENT_KEYS:
        value = raw.get(key)
        if value is None or value == "" or value == []:
            continue
        out[key] = value
    return out


def has_content(requirements: dict[str, Any], summary: str) -> bool:
    """Is this worth putting in front of Shmuel at all?

    A greeting with no stated requirement should not become a queue item —
    the queue is only useful if everything in it needs a decision.
    """
    return bool(requirements) or bool(summary.strip())


async def extract_lead(
    session: Any,
    *,
    transcript: str,
    source: LeadSource,
    source_ref: str | None = None,
    phone: str | None = None,
) -> LeadExtraction | None:
    """Extract a lead from `transcript` and queue it for review.

    Returns the queued row, or None when there was nothing worth queueing
    (no LLM key, model failure, or a conversation with no requirement in it).

    Idempotent per source_ref while still PENDING: re-running over the same
    thread updates the pending row rather than stacking duplicates in the
    queue. An already-reviewed row is left alone — Shmuel's decision stands.
    """
    parsed = await _call_llm(transcript)
    if parsed is None:
        return None

    summary = str(parsed.get("summary") or "").strip()
    requirements = _clean_requirements(parsed.get("requirements"))
    if not has_content(requirements, summary):
        return None

    display_name = parsed.get("display_name")
    display_name = str(display_name).strip() if display_name else None

    existing: LeadExtraction | None = None
    if source_ref:
        existing = (
            await session.execute(
                select(LeadExtraction).where(
                    LeadExtraction.source_ref == source_ref,
                    LeadExtraction.status == LeadStatus.PENDING,
                )
            )
        ).scalar_one_or_none()

    if existing is not None:
        existing.summary = summary
        existing.requirements = requirements
        if display_name:
            existing.display_name = display_name
        if phone:
            existing.phone = phone
        return existing

    lead = LeadExtraction(
        source=source,
        source_ref=source_ref,
        phone=phone,
        display_name=display_name,
        summary=summary,
        requirements=requirements,
        status=LeadStatus.PENDING,
    )
    session.add(lead)
    return lead


def format_notes(lead: LeadExtraction) -> str:
    """Render an extraction as the note body written onto a Contact.

    Plain readable lines rather than JSON, because this is what Shmuel reads
    in the address book months later.
    """
    lines: list[str] = []
    if lead.summary:
        lines.append(lead.summary)
    req = lead.requirements or {}
    labels = {
        "deal_type": "Looking to",
        "rooms": "Rooms",
        "neighborhoods": "Neighbourhoods",
        "furnished": "Furnished",
        "parking": "Parking",
        "household": "Household",
        "timing": "Timing",
        "budget": "Budget",
        "other": "Also wants",
    }
    detail: list[str] = []
    for key in REQUIREMENT_KEYS:
        if key not in req:
            continue
        value = req[key]
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            value = "yes" if value else "no"
        detail.append(f"{labels[key]}: {value}")
    if detail:
        if lines:
            lines.append("")
        lines.extend(detail)
    origin = "phone call" if lead.source == LeadSource.CALL else "WhatsApp"
    lines.append("")
    lines.append(f"(extracted from a {origin} on {lead.created_at:%Y-%m-%d})"
                 if lead.created_at else f"(extracted from a {origin})")
    return "\n".join(lines)


async def approve_lead(session: Any, lead: LeadExtraction) -> Contact:
    """Turn an approved extraction into a Contact.

    Matches an existing contact on phone so a repeat caller accumulates notes
    instead of spawning duplicates.
    """
    contact: Contact | None = None
    if lead.phone:
        contact = (
            await session.execute(select(Contact).where(Contact.phone == lead.phone))
        ).scalar_one_or_none()

    notes = format_notes(lead)
    if contact is None:
        contact = Contact(
            name=lead.display_name or lead.phone or "Unknown caller",
            phone=lead.phone,
            segments=["lead"],
            notes=notes,
            source=f"lead:{lead.source.value}",
        )
        session.add(contact)
        await session.flush()
    else:
        contact.notes = f"{contact.notes}\n\n{notes}" if contact.notes else notes
        if not contact.name and lead.display_name:
            contact.name = lead.display_name

    lead.status = LeadStatus.APPROVED
    lead.contact_id = contact.id
    lead.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    return contact
