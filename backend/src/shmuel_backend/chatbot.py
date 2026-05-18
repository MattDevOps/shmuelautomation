"""Phase 3.1 WhatsApp chatbot — inbound message → bot reply pipeline.

Sits between the daemon webhook (which already stores every inbound
message in `whatsapp_messages`) and the daemon's outbound /send-dm
endpoint. For each new 1:1 message:

1. Skip group chats entirely (the bot only handles DMs).
2. Look up or create a `whatsapp_threads` row keyed by `chat_jid`.
3. Honor takeover state: if `mode == HUMAN`, the bot stays silent.
4. Honor the global `bot_config.chatbot_enabled` flag.
5. Honor a per-thread rate limit so we don't spam replies.
6. Classify intent via an OpenAI structured-output call.
7. SEARCH → match properties, reply with the top N. QUESTION/OTHER →
   flip thread to HUMAN with a takeover notice. GREETING → polite ack.

Every external dependency degrades gracefully: missing `openai_api_key`
means no reply (logged), daemon unreachable means no reply (logged).
The thread's `last_processed_wa_ts` watermark always advances so a
single message is never reprocessed.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import whatsapp_client
from shmuel_backend.config import settings
from shmuel_backend.enums import (
    ChatbotIntent,
    PropertyStatus,
    PropertyType,
    ThreadMode,
)
from shmuel_backend.models import (
    BotConfig,
    Contact,
    Property,
    WhatsappMessage,
    WhatsappThread,
)

log = logging.getLogger(__name__)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

DEFAULT_GREETING_EN = (
    "Hi! I'm Classic Jerusalem Realty's assistant. Tell me what you're "
    "looking for — neighborhood, budget, number of rooms, rent or buy — "
    "and I'll show you what we have."
)
DEFAULT_GREETING_HE = (
    "שלום! אני העוזר של Classic Jerusalem Realty. ספרו לי מה אתם מחפשים — "
    "שכונה, תקציב, מספר חדרים, השכרה או רכישה — ואני אראה לכם מה יש לנו."
)
DEFAULT_TAKEOVER_EN = (
    "Thanks for reaching out — Shmuel will get back to you personally as "
    "soon as possible."
)
DEFAULT_TAKEOVER_HE = (
    "תודה שפניתם — שמואל יחזור אליכם אישית בהקדם האפשרי."
)

CLASSIFY_SYSTEM_PROMPT = (
    "You triage WhatsApp messages for a Jerusalem real-estate brokerage. "
    "Classify the user's most recent message and, if it's a property "
    "search, extract structured criteria. Respond with ONLY valid JSON "
    "matching this schema:\n"
    '{"intent": "search"|"question"|"greeting"|"other",\n'
    ' "language": "he"|"en",\n'
    ' "criteria": {\n'
    '   "type": "rent"|"sale"|null,\n'
    '   "max_price": number|null,\n'
    '   "min_rooms": number|null,\n'
    '   "neighborhood": string|null,\n'
    '   "keywords": [string, ...]\n'
    ' }}\n\n'
    "Rules:\n"
    "- intent=search ONLY if the user is asking about available "
    "  properties matching some criteria. Vague hellos are greetings, "
    "  not searches.\n"
    "- intent=question for off-catalog asks (viewings, neighborhood "
    "  questions, legal/payment, scheduling). These need a human.\n"
    "- intent=other for spam, complaints, or anything ambiguous — also "
    "  routes to a human.\n"
    "- max_price in NIS (shekels). If the user says USD, convert at "
    "  3.7 NIS/USD. If they say K or thousand, multiply by 1000.\n"
    "- min_rooms: smallest acceptable room count, integer or x.5.\n"
    "- neighborhood: a Jerusalem neighborhood name in Hebrew or "
    "  English. Null if not mentioned.\n"
    "- language: detect from the most recent message."
)


@dataclass
class ProcessResult:
    """Outcome of a single inbound-message processing pass.

    `replied=True` means we successfully called the daemon's send-dm.
    `reason` is set on every skip path so the admin UI can show why."""

    thread_id: str | None = None
    intent: ChatbotIntent | None = None
    replied: bool = False
    reason: str | None = None
    matches: list[dict[str, Any]] = field(default_factory=list)


# --- Phone / language helpers ----------------------------------------

_E164_DIGITS = re.compile(r"\D+")


def normalize_phone(phone: str | None) -> str | None:
    """Strip everything that isn't a digit. Israel numbers come from
    WhatsApp without the + so this is the lowest-common-denominator
    form for matching against `contacts.phone`."""
    if not phone:
        return None
    digits = _E164_DIGITS.sub("", phone)
    return digits or None


def phone_from_jid(jid: str) -> str | None:
    """`972501234567@s.whatsapp.net` → `972501234567`."""
    if "@" not in jid:
        return None
    head = jid.split("@", 1)[0]
    return normalize_phone(head)


def _site_base_url() -> str:
    """Public base URL used in property reply links."""
    return (
        settings.chatbot_site_base_url.rstrip("/")
        or settings.newsletter_site_base_url.rstrip("/")
    )


# --- Bot config / thread upsert --------------------------------------

async def get_or_create_bot_config(session: AsyncSession) -> BotConfig:
    """Return the singleton BotConfig row, creating it on first read."""
    cfg = await session.get(BotConfig, "default")
    if cfg is None:
        cfg = BotConfig(id="default", chatbot_enabled=False)
        session.add(cfg)
        await session.flush()
    return cfg


async def get_or_create_thread(
    session: AsyncSession,
    *,
    chat_jid: str,
    from_jid: str,
    from_phone: str | None,
    from_name: str | None,
) -> WhatsappThread:
    """Fetch the thread for `chat_jid`, creating it on first contact.

    Also tries a phone-match against `contacts` so future replies show
    Shmuel's existing CRM context without a manual link step."""
    row = await session.execute(
        select(WhatsappThread).where(WhatsappThread.chat_jid == chat_jid)
    )
    thread = row.scalar_one_or_none()
    if thread is not None:
        return thread

    phone = normalize_phone(from_phone) or phone_from_jid(from_jid)
    contact_id = None
    if phone:
        match = await session.execute(
            select(Contact.id).where(Contact.phone == phone).limit(1)
        )
        contact_id = match.scalar_one_or_none()

    thread = WhatsappThread(
        chat_jid=chat_jid,
        phone_number=phone,
        display_name=from_name,
        mode=ThreadMode.BOT,
        contact_id=contact_id,
    )
    session.add(thread)
    await session.flush()
    return thread


# --- OpenAI classifier -----------------------------------------------

async def classify_message(text: str) -> dict[str, Any] | None:
    """Call the LLM, return parsed JSON or None on any failure.

    None means "we don't know" — caller should treat as OTHER and
    handoff to a human rather than guess."""
    if not settings.openai_api_key:
        log.info("chatbot.classify: OpenAI key unset; would have classified %d chars", len(text))
        return None

    payload = {
        "model": settings.openai_chat_model,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(OPENAI_ENDPOINT, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.warning("chatbot.classify: openai %s: %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("chatbot.classify: openai request failed: %s", exc)
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
        log.warning("chatbot.classify: bad json from model: %s", content[:200])
        return None


# --- Property matcher ------------------------------------------------

async def match_properties(
    session: AsyncSession,
    criteria: dict[str, Any],
    *,
    limit: int,
) -> list[Property]:
    """Available properties matching the parsed criteria.

    Best-effort filtering — every criterion is optional and gets
    skipped if missing or malformed. Returns at most `limit` rows
    ordered by created_at desc so the freshest listings surface first."""
    stmt = select(Property).where(Property.status == PropertyStatus.AVAILABLE)

    raw_type = criteria.get("type")
    if raw_type in (PropertyType.RENT.value, PropertyType.SALE.value):
        stmt = stmt.where(Property.type == PropertyType(raw_type))

    raw_price = criteria.get("max_price")
    if isinstance(raw_price, int | float) and raw_price > 0:
        stmt = stmt.where(Property.price <= Decimal(str(raw_price)))

    raw_rooms = criteria.get("min_rooms")
    if isinstance(raw_rooms, int | float) and raw_rooms > 0:
        stmt = stmt.where(Property.rooms >= Decimal(str(raw_rooms)))

    neighborhood = criteria.get("neighborhood")
    if isinstance(neighborhood, str) and neighborhood.strip():
        like = f"%{neighborhood.strip()}%"
        stmt = stmt.where(Property.neighborhood.ilike(like))

    stmt = stmt.order_by(Property.created_at.desc()).limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


# --- Reply formatting ------------------------------------------------

def _format_property_line(prop: Property, lang: str) -> str:
    """One property as a 2-3 line block — same shape EN/HE.

    Hebrew puts the price after the neighborhood; English leads with
    the price. Both link to the public listing page."""
    base = _site_base_url()
    link = f"{base}/properties/{prop.id}" if base else ""

    rooms = (
        f"{prop.rooms:g} חדרים" if lang == "he" and prop.rooms is not None
        else (f"{prop.rooms:g} rooms" if prop.rooms is not None else "")
    )
    neighborhood = prop.neighborhood or ""
    price = f"{int(prop.price):,} {prop.currency or 'ILS'}"
    type_label = (
        ("השכרה" if prop.type == PropertyType.RENT else "מכירה")
        if lang == "he"
        else ("rent" if prop.type == PropertyType.RENT else "sale")
    )

    if lang == "he":
        line1 = " · ".join(p for p in (neighborhood, rooms, type_label) if p)
        return "\n".join(p for p in (f"• {line1}", price, link) if p).strip()
    line1 = " · ".join(p for p in (neighborhood, rooms, type_label) if p)
    return "\n".join(p for p in (f"• {line1}", price, link) if p).strip()


def format_search_reply(props: list[Property], lang: str) -> str:
    """Compose a search reply with up to N property cards."""
    if not props:
        if lang == "he":
            return (
                "לא מצאתי כרגע מודעות שמתאימות לבקשה. אנא תארו שוב או "
                "פרטו שכונה / טווח מחירים אחר."
            )
        return (
            "I couldn't find listings matching that right now. Could "
            "you share another neighborhood or budget range?"
        )

    intro = (
        "הנה כמה אפשרויות מתאימות:" if lang == "he" else "Here are some matches:"
    )
    outro = (
        "רוצים לראות אחד מהם בהרחבה או לקבוע ביקור? אעדכן את שמואל."
        if lang == "he"
        else "Want details on one of these or to schedule a viewing? I'll loop in Shmuel."
    )
    cards = "\n\n".join(_format_property_line(p, lang) for p in props)
    return f"{intro}\n\n{cards}\n\n{outro}"


def _greeting_text(cfg: BotConfig, lang: str) -> str:
    """Configured greeting if set; otherwise the localized default."""
    if lang == "he":
        return (cfg.greeting_he or "").strip() or DEFAULT_GREETING_HE
    return (cfg.greeting_en or "").strip() or DEFAULT_GREETING_EN


def _takeover_text(cfg: BotConfig, lang: str) -> str:
    """Configured takeover notice if set; otherwise the localized default."""
    if lang == "he":
        return (cfg.takeover_notice_he or "").strip() or DEFAULT_TAKEOVER_HE
    return (cfg.takeover_notice_en or "").strip() or DEFAULT_TAKEOVER_EN


# --- Rate limit ------------------------------------------------------

def _within_rate_limit(thread: WhatsappThread, *, now: datetime) -> bool:
    """True iff the bot already replied to this thread within the
    configured interval. Per-thread limit keeps us out of spam-band
    territory when a user sends a burst of messages."""
    last = thread.last_bot_reply_at
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    elapsed = (now - last).total_seconds()
    return elapsed < settings.chatbot_min_reply_interval_seconds


# --- Top-level entry point -------------------------------------------

async def process_inbound(
    session: AsyncSession,
    message: WhatsappMessage,
    *,
    now: datetime | None = None,
) -> ProcessResult:
    """Process a single stored inbound message and (maybe) send a reply.

    Idempotent: callers may invoke this on the same message twice (e.g.
    re-deliveries from the daemon) and at most one reply will go out
    because the thread's `last_processed_wa_ts` advances on every pass.
    """
    now = now or datetime.now(UTC)
    result = ProcessResult()

    # Group chats: bot stays out entirely.
    if message.is_group:
        result.reason = "group_chat"
        return result

    cfg = await get_or_create_bot_config(session)
    thread = await get_or_create_thread(
        session,
        chat_jid=message.chat_jid,
        from_jid=message.from_jid,
        from_phone=message.from_phone,
        from_name=message.from_name,
    )
    result.thread_id = str(thread.id)

    # Always advance the watermark and last_message_at — that way even
    # the no-op paths still mark the message processed.
    if (
        thread.last_processed_wa_ts is not None
        and message.wa_timestamp <= thread.last_processed_wa_ts
    ):
        result.reason = "already_processed"
        return result

    thread.last_processed_wa_ts = message.wa_timestamp
    thread.last_message_at = now.replace(tzinfo=None)

    if not cfg.chatbot_enabled:
        result.reason = "chatbot_disabled"
        await session.commit()
        return result

    if thread.mode == ThreadMode.HUMAN:
        result.reason = "thread_in_human_mode"
        await session.commit()
        return result

    if _within_rate_limit(thread, now=now):
        result.reason = "rate_limited"
        await session.commit()
        return result

    text = (message.text or "").strip()
    if not text:
        # No text body — likely a sticker, voice note, or media-only msg.
        # We can't classify it, so hand off to a human.
        thread.mode = ThreadMode.HUMAN
        thread.takeover_reason = "non_text_message"
        result.intent = ChatbotIntent.OTHER
        result.reason = "non_text_handoff"
        await _send_dm_safe(thread, _takeover_text(cfg, "en"), result)
        await session.commit()
        return result

    parsed = await classify_message(text)
    if parsed is None:
        # Couldn't classify (no key, network fail, bad JSON) — be safe
        # and hand off. Don't reply with a takeover notice though,
        # because we have no key to call the daemon in the first place.
        thread.mode = ThreadMode.HUMAN
        thread.takeover_reason = "classify_failed"
        result.intent = ChatbotIntent.OTHER
        result.reason = "classify_failed"
        await session.commit()
        return result

    intent_raw = (parsed.get("intent") or "").lower()
    try:
        intent = ChatbotIntent(intent_raw)
    except ValueError:
        intent = ChatbotIntent.OTHER
    lang = "he" if (parsed.get("language") or "en").lower() == "he" else "en"
    result.intent = intent

    if intent == ChatbotIntent.SEARCH:
        criteria = parsed.get("criteria") or {}
        props = await match_properties(
            session, criteria, limit=settings.chatbot_max_matches_per_reply
        )
        reply = format_search_reply(props, lang)
        result.matches = [
            {
                "id": str(p.id),
                "neighborhood": p.neighborhood,
                "price": int(p.price),
                "type": p.type.value,
                "rooms": float(p.rooms) if p.rooms is not None else None,
            }
            for p in props
        ]
        await _send_dm_safe(thread, reply, result)
        await session.commit()
        return result

    if intent == ChatbotIntent.GREETING:
        await _send_dm_safe(thread, _greeting_text(cfg, lang), result)
        await session.commit()
        return result

    # QUESTION or OTHER → takeover.
    thread.mode = ThreadMode.HUMAN
    thread.takeover_reason = intent.value
    await _send_dm_safe(thread, _takeover_text(cfg, lang), result)
    await session.commit()
    return result


async def _send_dm_safe(
    thread: WhatsappThread,
    text: str,
    result: ProcessResult,
) -> None:
    """Best-effort DM send. Updates `last_bot_reply_at` only on success.

    A failed send (daemon down, unconfigured, ban) leaves the thread in
    a state where the next inbound message will retry — that's the
    right behavior for transient failures."""
    phone = thread.phone_number or phone_from_jid(thread.chat_jid)
    if not phone:
        result.reason = "no_phone"
        return
    sent = await whatsapp_client.send_to_phone(
        to_phone_number=phone, message=text
    )
    if sent is None:
        result.reason = result.reason or "daemon_send_failed"
        return
    result.replied = True
    thread.last_bot_reply_at = datetime.now(UTC).replace(tzinfo=None)
