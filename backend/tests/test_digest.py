"""Daily digest tests — covers each skip reason + the happy path."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.config import settings as cfg
from shmuel_backend.digest import send_daily_digest
from shmuel_backend.models import ConversationSummary

RESEND_ENDPOINT = "https://api.resend.com/emails"


@pytest.fixture
def with_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "broker_email", "shmuel@example.com")


@pytest.fixture
def with_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "resend_api_key", "re_test")


def _seed_summary(
    session: AsyncSession,
    *,
    chat_jid: str = "972501234567@s.whatsapp.net",
    summary: str = "Lead asked about Talbiya.",
    action_items: list[str] | None = None,
    amounts: list[str] | None = None,
    dates: list[str] | None = None,
    created_at: datetime | None = None,
) -> ConversationSummary:
    now = (created_at or datetime.now(UTC)).replace(tzinfo=None)
    row = ConversationSummary(
        chat_jid=chat_jid,
        phone_number="972501234567",
        period_start=now - timedelta(minutes=5),
        period_end=now,
        message_count=3,
        summary=summary,
        action_items=action_items or [],
        mentioned_amounts=amounts or [],
        mentioned_dates=dates or [],
        created_at=now,
    )
    session.add(row)
    return row


@pytest.mark.asyncio
async def test_skip_when_recipient_unset(session: AsyncSession) -> None:
    result = await send_daily_digest(session)
    assert result.sent is False
    assert result.reason == "no_recipient"


@pytest.mark.asyncio
async def test_skip_when_no_summaries_in_window(
    session: AsyncSession, with_recipient: None
) -> None:
    # Seed a summary way outside the window
    old = datetime.now(UTC) - timedelta(days=7)
    _seed_summary(session, created_at=old)
    await session.commit()
    result = await send_daily_digest(session)
    assert result.sent is False
    assert result.reason == "no_summaries"


@pytest.mark.asyncio
async def test_skip_when_resend_unconfigured(
    session: AsyncSession, with_recipient: None
) -> None:
    _seed_summary(session)
    await session.commit()
    result = await send_daily_digest(session)
    assert result.sent is False
    assert result.reason == "resend_no_op"
    assert result.summaries_included == 1
    assert result.threads_included == 1


@pytest.mark.asyncio
async def test_happy_path_sends_email(
    session: AsyncSession, with_recipient: None, with_resend: None
) -> None:
    _seed_summary(
        session,
        summary="Lead wants 3BR Talbiya.",
        action_items=["call back Tue"],
        amounts=["12k"],
        dates=["Tuesday"],
    )
    _seed_summary(
        session,
        chat_jid="972509999999@s.whatsapp.net",
        summary="Lead asking about sales.",
    )
    await session.commit()

    with respx.mock(assert_all_called=True) as rmock:
        route = rmock.post(RESEND_ENDPOINT).mock(
            return_value=Response(200, json={"id": "abc"})
        )
        result = await send_daily_digest(session)

    assert result.sent is True
    assert result.threads_included == 2
    payload = json.loads(route.calls[0].request.read())
    assert payload["to"] == ["shmuel@example.com"]
    assert "Talbiya" in payload["html"]
    assert "call back Tue" in payload["html"]
    assert "12k" in payload["html"]
    assert "Open action items" in payload["html"]


@pytest.mark.asyncio
async def test_skip_when_resend_rejects(
    session: AsyncSession, with_recipient: None, with_resend: None
) -> None:
    _seed_summary(session)
    await session.commit()
    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(RESEND_ENDPOINT).mock(return_value=Response(500, text="boom"))
        result = await send_daily_digest(session)
    assert result.sent is False
    assert result.reason == "resend_failed"


@pytest.mark.asyncio
async def test_endpoint_returns_structured_outcome(
    client: TestClient, session: AsyncSession
) -> None:
    """Without recipient or resend set the endpoint still 200s and
    reports the reason — the admin UI shows it."""
    resp = client.post("/whatsapp/summaries/send-digest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is False
    assert data["reason"] == "no_recipient"


@pytest.mark.asyncio
async def test_endpoint_happy_path(
    client: TestClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "broker_email", "shmuel@example.com")
    monkeypatch.setattr(cfg, "resend_api_key", "re_test")
    _seed_summary(session)
    await session.commit()

    with respx.mock(assert_all_called=True) as rmock:
        rmock.post(RESEND_ENDPOINT).mock(return_value=Response(200, json={"id": "x"}))
        resp = client.post("/whatsapp/summaries/send-digest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is True
    assert data["recipient"] == "shmuel@example.com"
    assert data["threads_included"] == 1


@pytest.mark.asyncio
async def test_aggregates_action_items_per_thread(
    session: AsyncSession, with_recipient: None, with_resend: None
) -> None:
    """Multiple summary rows for the same thread → all action items
    surface together in the email."""
    now = datetime.now(UTC)
    earlier = now - timedelta(hours=3)
    _seed_summary(
        session,
        chat_jid="111@s.whatsapp.net",
        summary="Earlier",
        action_items=["call Monday"],
        created_at=earlier,
    )
    _seed_summary(
        session,
        chat_jid="111@s.whatsapp.net",
        summary="Latest",
        action_items=["send photos"],
        created_at=now,
    )
    await session.commit()

    with respx.mock(assert_all_called=True) as rmock:
        route = rmock.post(RESEND_ENDPOINT).mock(
            return_value=Response(200, json={"id": "abc"})
        )
        await send_daily_digest(session)

    payload = json.loads(route.calls[0].request.read())
    assert "call Monday" in payload["html"]
    assert "send photos" in payload["html"]
