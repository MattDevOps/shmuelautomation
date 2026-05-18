"""Tests for the Phase 3.2 summarizer.

Covers no-op (no key, no messages), success path, idempotency,
contact linking, and the admin routes (list + run-now + scoped list).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.config import settings as cfg
from shmuel_backend.enums import ThreadMode
from shmuel_backend.models import (
    Contact,
    ConversationSummary,
    WhatsappMessage,
    WhatsappThread,
)
from shmuel_backend.summarizer import (
    call_openai_summarize,
    summarize_all_threads,
    summarize_thread,
)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"


@pytest.fixture
def with_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "openai_api_key", "sk-test")


def _mock_openai(payload: dict) -> Response:
    return Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": json.dumps(payload)}}
            ]
        },
    )


async def _make_thread(
    session: AsyncSession,
    *,
    chat_jid: str = "972501234567@s.whatsapp.net",
    phone: str | None = "972501234567",
    last_message_at: datetime | None = None,
) -> WhatsappThread:
    t = WhatsappThread(
        chat_jid=chat_jid,
        phone_number=phone,
        display_name="Lead",
        mode=ThreadMode.BOT,
        last_message_at=(last_message_at or datetime.now(UTC)).replace(tzinfo=None),
    )
    session.add(t)
    await session.flush()
    return t


async def _add_msg(
    session: AsyncSession,
    *,
    thread: WhatsappThread,
    text: str,
    created_at: datetime,
    message_id: str,
) -> WhatsappMessage:
    m = WhatsappMessage(
        message_id=message_id,
        chat_jid=thread.chat_jid,
        from_jid=thread.chat_jid,
        from_phone=thread.phone_number,
        from_name=thread.display_name,
        text=text,
        wa_timestamp=int(created_at.timestamp()),
        created_at=created_at.replace(tzinfo=None),
    )
    session.add(m)
    await session.flush()
    return m


# --- Unit tests for the LLM wrapper ---------------------------------


@pytest.mark.asyncio
async def test_call_openai_summarize_no_op_when_unconfigured() -> None:
    assert await call_openai_summarize("transcript") is None


@pytest.mark.asyncio
async def test_call_openai_summarize_returns_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "openai_api_key", "sk-test")
    payload = {
        "summary": "Lead asked about Talbiya 3BR.",
        "action_items": ["call back Tuesday"],
        "mentioned_amounts": ["12k"],
        "mentioned_dates": ["Tuesday"],
    }
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload))
        out = await call_openai_summarize("hi")
    assert out == payload


# --- summarize_thread ------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_thread_skips_when_no_messages(
    session: AsyncSession, with_openai: None
) -> None:
    thread = await _make_thread(session)
    out = await summarize_thread(session, thread)
    assert out.skipped_reason == "no_new_messages"
    assert out.summary_id is None


@pytest.mark.asyncio
async def test_summarize_thread_skips_when_llm_unavailable(
    session: AsyncSession,
) -> None:
    """No openai_api_key → record skip, never write a fabricated row."""
    thread = await _make_thread(session)
    now = datetime.now(UTC)
    await _add_msg(
        session, thread=thread, text="hi", created_at=now, message_id="M1"
    )
    out = await summarize_thread(session, thread, until=now + timedelta(seconds=1))
    assert out.skipped_reason == "llm_unavailable"
    rows = (await session.execute(select(ConversationSummary))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_summarize_thread_writes_row_and_links_contact(
    session: AsyncSession, with_openai: None
) -> None:
    contact = Contact(name="Yossi", phone="972501234567")
    session.add(contact)
    await session.flush()

    thread = await _make_thread(session)
    now = datetime.now(UTC)
    await _add_msg(
        session, thread=thread, text="3 bedroom in Talbiya max 12k",
        created_at=now, message_id="M1",
    )

    payload = {
        "summary": "Lead asked about 3BR Talbiya up to 12k.",
        "action_items": ["send 2-3 matches"],
        "mentioned_amounts": ["12k"],
        "mentioned_dates": [],
    }
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload))
        out = await summarize_thread(
            session, thread, until=now + timedelta(seconds=1)
        )

    assert out.summary_id is not None
    assert out.message_count == 1

    row = (await session.execute(select(ConversationSummary))).scalar_one()
    assert row.summary == payload["summary"]
    assert row.action_items == payload["action_items"]
    assert row.mentioned_amounts == ["12k"]
    assert row.contact_id == contact.id
    assert row.message_count == 1


@pytest.mark.asyncio
async def test_summarize_thread_is_idempotent_within_window(
    session: AsyncSession, with_openai: None
) -> None:
    """Re-running for the same period_end updates, doesn't duplicate."""
    thread = await _make_thread(session)
    now = datetime.now(UTC)
    until = now + timedelta(seconds=1)
    await _add_msg(
        session, thread=thread, text="first", created_at=now, message_id="M1"
    )
    payload_a = {
        "summary": "first run",
        "action_items": [],
        "mentioned_amounts": [],
        "mentioned_dates": [],
    }
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload_a))
        await summarize_thread(session, thread, until=until)

    # Re-running with same window — already_summarized
    out = await summarize_thread(session, thread, until=until)
    assert out.skipped_reason == "already_summarized"

    rows = (await session.execute(select(ConversationSummary))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_summarize_thread_handles_new_messages_in_later_window(
    session: AsyncSession, with_openai: None
) -> None:
    """A second pass after new messages writes a fresh summary row."""
    thread = await _make_thread(session)
    now = datetime.now(UTC)
    until_a = now + timedelta(seconds=1)
    await _add_msg(
        session, thread=thread, text="first", created_at=now, message_id="M1"
    )
    payload = {
        "summary": "first",
        "action_items": [],
        "mentioned_amounts": [],
        "mentioned_dates": [],
    }
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload))
        await summarize_thread(session, thread, until=until_a)

    # New message later, run again
    later = now + timedelta(hours=1)
    await _add_msg(
        session, thread=thread, text="follow up", created_at=later, message_id="M2"
    )
    until_b = later + timedelta(seconds=1)
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(
            return_value=_mock_openai({**payload, "summary": "second"})
        )
        await summarize_thread(session, thread, until=until_b)

    rows = (
        await session.execute(
            select(ConversationSummary).order_by(ConversationSummary.period_end)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert rows[1].summary == "second"


# --- summarize_all_threads ------------------------------------------


@pytest.mark.asyncio
async def test_summarize_all_threads_only_recent(
    session: AsyncSession, with_openai: None
) -> None:
    now = datetime.now(UTC)
    fresh = await _make_thread(
        session,
        chat_jid="111@s.whatsapp.net",
        last_message_at=now,
    )
    stale = await _make_thread(
        session,
        chat_jid="222@s.whatsapp.net",
        last_message_at=now - timedelta(days=10),
    )
    await _add_msg(
        session, thread=fresh, text="hi", created_at=now, message_id="A1"
    )
    await _add_msg(
        session,
        thread=stale,
        text="stale",
        created_at=now - timedelta(days=10),
        message_id="B1",
    )

    payload = {
        "summary": "ok",
        "action_items": [],
        "mentioned_amounts": [],
        "mentioned_dates": [],
    }
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload))
        run = await summarize_all_threads(
            session, until=now + timedelta(seconds=1)
        )

    # Stale thread skipped entirely; fresh thread summarized.
    assert run.attempted == 1
    assert run.summarized == 1
    assert run.threads[0].chat_jid == "111@s.whatsapp.net"


# --- Routes ----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_summaries_filters_by_contact(
    client: TestClient, session: AsyncSession
) -> None:
    contact = Contact(name="Y", phone="972501234567")
    session.add(contact)
    await session.flush()

    now = datetime.now(UTC).replace(tzinfo=None)
    s_match = ConversationSummary(
        chat_jid="111@s.whatsapp.net",
        phone_number="972501234567",
        contact_id=contact.id,
        period_start=now,
        period_end=now + timedelta(minutes=1),
        message_count=2,
        summary="match",
    )
    s_other = ConversationSummary(
        chat_jid="222@s.whatsapp.net",
        phone_number="999",
        period_start=now,
        period_end=now + timedelta(minutes=2),
        message_count=1,
        summary="other",
    )
    session.add_all([s_match, s_other])
    await session.commit()

    resp = client.get(f"/whatsapp/summaries?contact_id={contact.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["summaries"][0]["summary"] == "match"


@pytest.mark.asyncio
async def test_run_summarize_now_endpoint(
    client: TestClient,
    session: AsyncSession,
    with_openai: None,
) -> None:
    """The POST /whatsapp/summaries/run kicks the whole run.

    We give the test thread a real message so it actually summarizes,
    and respx-mock OpenAI to a fixed payload.
    """
    now = datetime.now(UTC)
    thread = await _make_thread(session, last_message_at=now)
    await _add_msg(
        session, thread=thread, text="hello", created_at=now, message_id="M1"
    )
    await session.commit()

    payload = {
        "summary": "Lead said hello.",
        "action_items": [],
        "mentioned_amounts": [],
        "mentioned_dates": [],
    }
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload))
        resp = client.post("/whatsapp/summaries/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["attempted"] == 1
    assert data["summarized"] == 1


@pytest.mark.asyncio
async def test_summarize_single_thread_endpoint(
    client: TestClient,
    session: AsyncSession,
    with_openai: None,
) -> None:
    now = datetime.now(UTC)
    thread = await _make_thread(session, last_message_at=now)
    await _add_msg(
        session, thread=thread, text="hi", created_at=now, message_id="M1"
    )
    await session.commit()

    payload = {
        "summary": "Hello.",
        "action_items": [],
        "mentioned_amounts": [],
        "mentioned_dates": [],
    }
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(OPENAI_ENDPOINT).mock(return_value=_mock_openai(payload))
        resp = client.post(f"/whatsapp/threads/{thread.id}/summarize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary_id"] is not None
    assert data["message_count"] == 1


@pytest.mark.asyncio
async def test_thread_summaries_404_when_unknown(client: TestClient) -> None:
    resp = client.get(
        "/whatsapp/threads/00000000-0000-0000-0000-000000000000/summaries"
    )
    assert resp.status_code == 404
