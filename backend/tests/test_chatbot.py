"""Tests for the Phase 3.1 WhatsApp chatbot.

Covers the no-op gates (chatbot disabled, group chat, human takeover,
rate limit, daemon unconfigured), the intent paths (SEARCH /
GREETING / QUESTION / OTHER), and idempotency on duplicate inbound.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import respx
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.chatbot import (
    classify_message,
    format_search_reply,
    match_properties,
    normalize_phone,
    phone_from_jid,
    process_inbound,
)
from shmuel_backend.config import settings as cfg
from shmuel_backend.enums import (
    BrokerFeeStatus,
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

DAEMON_URL = "http://daemon.local:8787"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"


# --- Fixtures --------------------------------------------------------


@pytest.fixture
def with_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "whatsapp_daemon_url", DAEMON_URL)
    monkeypatch.setattr(cfg, "whatsapp_daemon_token", "tok123")


@pytest.fixture
def with_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "openai_api_key", "sk-test")


@pytest.fixture
def chatbot_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "chatbot_min_reply_interval_seconds", 30)


async def _enable_bot(session: AsyncSession) -> BotConfig:
    """Insert a `bot_config` row with chatbot_enabled=True."""
    row = BotConfig(id="default", chatbot_enabled=True)
    session.add(row)
    await session.flush()
    return row


async def _make_message(
    session: AsyncSession,
    *,
    text: str,
    chat_jid: str = "972501234567@s.whatsapp.net",
    from_jid: str | None = None,
    from_phone: str | None = "972501234567",
    from_name: str | None = "Lead",
    is_group: bool = False,
    timestamp: int | None = None,
    message_id: str = "MSG1",
) -> WhatsappMessage:
    msg = WhatsappMessage(
        message_id=message_id,
        chat_jid=chat_jid,
        from_jid=from_jid or chat_jid,
        from_phone=from_phone,
        from_name=from_name,
        is_group=is_group,
        text=text,
        wa_timestamp=timestamp if timestamp is not None else 1_700_000_000,
    )
    session.add(msg)
    await session.flush()
    return msg


def _mock_openai_json(payload: dict) -> Response:
    """OpenAI chat-completions response with `content` as JSON text."""
    return Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": json.dumps(payload)}}
            ]
        },
    )


# --- Helpers ---------------------------------------------------------


def test_normalize_phone() -> None:
    assert normalize_phone("+972 50 123-4567") == "972501234567"
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
    assert normalize_phone("call-me!") is None


def test_phone_from_jid() -> None:
    assert phone_from_jid("972501234567@s.whatsapp.net") == "972501234567"
    assert phone_from_jid("12345-67890@g.us") == "1234567890"
    assert phone_from_jid("no-at-here") is None


def test_format_search_reply_empty_he() -> None:
    out = format_search_reply([], "he")
    assert "לא מצאתי" in out


def test_format_search_reply_empty_en() -> None:
    out = format_search_reply([], "en")
    assert "couldn't find" in out.lower()


# --- Gate tests (no LLM needed) --------------------------------------


@pytest.mark.asyncio
async def test_skip_group_chat(session: AsyncSession) -> None:
    msg = await _make_message(session, text="hi", is_group=True)
    result = await process_inbound(session, msg)
    assert result.reason == "group_chat"
    assert result.replied is False


@pytest.mark.asyncio
async def test_skip_when_chatbot_disabled(session: AsyncSession) -> None:
    msg = await _make_message(session, text="any text")
    result = await process_inbound(session, msg)
    assert result.reason == "chatbot_disabled"
    assert result.replied is False


@pytest.mark.asyncio
async def test_skip_when_thread_in_human_mode(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    await _enable_bot(session)
    # Pre-create a thread in HUMAN mode.
    thread = WhatsappThread(
        chat_jid="972501234567@s.whatsapp.net",
        phone_number="972501234567",
        mode=ThreadMode.HUMAN,
    )
    session.add(thread)
    await session.flush()

    msg = await _make_message(session, text="hi")
    result = await process_inbound(session, msg)
    assert result.reason == "thread_in_human_mode"
    assert result.replied is False


@pytest.mark.asyncio
async def test_rate_limit_blocks_second_reply(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    await _enable_bot(session)
    now = datetime.now(UTC)
    thread = WhatsappThread(
        chat_jid="972501234567@s.whatsapp.net",
        phone_number="972501234567",
        mode=ThreadMode.BOT,
        last_bot_reply_at=(now - timedelta(seconds=5)).replace(tzinfo=None),
    )
    session.add(thread)
    await session.flush()

    msg = await _make_message(session, text="hi", timestamp=1_700_001_000)
    result = await process_inbound(session, msg, now=now)
    assert result.reason == "rate_limited"


# --- Watermark / idempotency ----------------------------------------


@pytest.mark.asyncio
async def test_already_processed_message_is_noop(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    await _enable_bot(session)
    thread = WhatsappThread(
        chat_jid="972501234567@s.whatsapp.net",
        phone_number="972501234567",
        mode=ThreadMode.BOT,
        last_processed_wa_ts=1_700_000_000,
    )
    session.add(thread)
    await session.flush()

    msg = await _make_message(session, text="hi", timestamp=1_700_000_000)
    result = await process_inbound(session, msg)
    assert result.reason == "already_processed"


# --- Intent paths ----------------------------------------------------


@pytest.mark.asyncio
async def test_search_intent_replies_with_matches(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    await _enable_bot(session)
    prop = Property(
        type=PropertyType.RENT,
        status=PropertyStatus.AVAILABLE,
        price=10000,
        currency="ILS",
        rooms=3,
        neighborhood="Talbiya",
        broker_fee_status=BrokerFeeStatus.YES,
    )
    session.add(prop)
    await session.flush()

    msg = await _make_message(
        session, text="3 bedroom in Talbiya under 12k for rent"
    )

    classify_resp = _mock_openai_json(
        {
            "intent": "search",
            "language": "en",
            "criteria": {
                "type": "rent",
                "max_price": 12000,
                "min_rooms": 3,
                "neighborhood": "Talbiya",
                "keywords": [],
            },
        }
    )
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=classify_resp)
        send_route = rmock.post(f"{DAEMON_URL}/send-dm").mock(
            return_value=Response(200, json={"ok": True, "messageId": "out"})
        )
        result = await process_inbound(session, msg)

    assert result.intent == ChatbotIntent.SEARCH
    assert result.replied is True
    assert len(result.matches) == 1
    assert send_route.called

    # Thread should now have a watermark + last_bot_reply_at, still BOT.
    thread = (
        await session.execute(
            __import__(
                "sqlalchemy"
            ).select(WhatsappThread).where(
                WhatsappThread.chat_jid == msg.chat_jid
            )
        )
    ).scalar_one()
    assert thread.mode == ThreadMode.BOT
    assert thread.last_bot_reply_at is not None
    assert thread.last_processed_wa_ts == msg.wa_timestamp


@pytest.mark.asyncio
async def test_greeting_intent_sends_greeting(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    await _enable_bot(session)
    msg = await _make_message(session, text="היי")

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(
            return_value=_mock_openai_json(
                {"intent": "greeting", "language": "he", "criteria": {}}
            )
        )
        send_route = rmock.post(f"{DAEMON_URL}/send-dm").mock(
            return_value=Response(200, json={"ok": True, "messageId": "out"})
        )
        result = await process_inbound(session, msg)

    assert result.intent == ChatbotIntent.GREETING
    assert result.replied is True
    assert send_route.called
    sent = json.loads(send_route.calls.last.request.content)
    assert "Classic Jerusalem Realty" in sent["message"] or "ספרו לי" in sent["message"]


@pytest.mark.asyncio
async def test_question_intent_triggers_takeover(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    await _enable_bot(session)
    msg = await _make_message(
        session, text="Can I see it tomorrow at 4pm?"
    )

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(
            return_value=_mock_openai_json(
                {"intent": "question", "language": "en", "criteria": {}}
            )
        )
        rmock.post(f"{DAEMON_URL}/send-dm").mock(
            return_value=Response(200, json={"ok": True, "messageId": "out"})
        )
        result = await process_inbound(session, msg)

    assert result.intent == ChatbotIntent.QUESTION
    assert result.replied is True

    thread = (
        await session.execute(
            __import__(
                "sqlalchemy"
            ).select(WhatsappThread).where(
                WhatsappThread.chat_jid == msg.chat_jid
            )
        )
    ).scalar_one()
    assert thread.mode == ThreadMode.HUMAN
    assert thread.takeover_reason == "question"


@pytest.mark.asyncio
async def test_classify_failure_triggers_silent_takeover(
    session: AsyncSession, with_daemon: None, with_openai: None
) -> None:
    """OpenAI 500 → takeover, but no reply (we don't know what to say)."""
    await _enable_bot(session)
    msg = await _make_message(session, text="?")

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=Response(500, text="err"))
        send_route = rmock.post(f"{DAEMON_URL}/send-dm").mock(
            return_value=Response(200, json={"ok": True})
        )
        result = await process_inbound(session, msg)

    assert result.reason == "classify_failed"
    assert result.replied is False
    assert not send_route.called


# --- Contact linking -------------------------------------------------


@pytest.mark.asyncio
async def test_creates_thread_and_links_existing_contact(
    session: AsyncSession,
) -> None:
    contact = Contact(name="Lead Person", phone="972501234567")
    session.add(contact)
    await session.flush()

    msg = await _make_message(session, text="anything")
    # chatbot disabled — only the thread bookkeeping matters here.
    await process_inbound(session, msg)

    from sqlalchemy import select as _sel

    thread = (
        await session.execute(
            _sel(WhatsappThread).where(WhatsappThread.chat_jid == msg.chat_jid)
        )
    ).scalar_one()
    assert thread.contact_id == contact.id
    assert thread.phone_number == "972501234567"


# --- Property matcher ------------------------------------------------


@pytest.mark.asyncio
async def test_match_properties_filters_correctly(session: AsyncSession) -> None:
    rent_match = Property(
        type=PropertyType.RENT,
        status=PropertyStatus.AVAILABLE,
        price=8000,
        rooms=3,
        neighborhood="Baka",
        broker_fee_status=BrokerFeeStatus.YES,
    )
    too_expensive = Property(
        type=PropertyType.RENT,
        status=PropertyStatus.AVAILABLE,
        price=20000,
        rooms=3,
        neighborhood="Baka",
        broker_fee_status=BrokerFeeStatus.YES,
    )
    wrong_type = Property(
        type=PropertyType.SALE,
        status=PropertyStatus.AVAILABLE,
        price=8000,
        rooms=3,
        neighborhood="Baka",
        broker_fee_status=BrokerFeeStatus.YES,
    )
    session.add_all([rent_match, too_expensive, wrong_type])
    await session.flush()

    matches = await match_properties(
        session,
        {
            "type": "rent",
            "max_price": 10000,
            "min_rooms": 2,
            "neighborhood": "Baka",
        },
        limit=10,
    )
    assert [m.id for m in matches] == [rent_match.id]


# --- Classifier client wrapper --------------------------------------


@pytest.mark.asyncio
async def test_classify_message_no_op_when_unconfigured(
    session: AsyncSession,
) -> None:
    assert await classify_message("hi") is None


@pytest.mark.asyncio
async def test_classify_message_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "openai_api_key", "sk-test")
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(
            return_value=_mock_openai_json(
                {"intent": "search", "language": "en", "criteria": {}}
            )
        )
        out = await classify_message("looking for rent")
    assert out is not None
    assert out["intent"] == "search"
