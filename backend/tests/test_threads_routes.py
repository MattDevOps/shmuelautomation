"""Admin routes for WhatsApp threads + bot config.

Covers list, get-with-messages, takeover/release, bot-config upsert.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.enums import ThreadMode
from shmuel_backend.models import BotConfig, WhatsappMessage, WhatsappThread


async def _seed_thread(
    session: AsyncSession,
    *,
    chat_jid: str = "972501234567@s.whatsapp.net",
    mode: ThreadMode = ThreadMode.BOT,
    last_message_at: datetime | None = None,
) -> WhatsappThread:
    thread = WhatsappThread(
        chat_jid=chat_jid,
        phone_number="972501234567",
        display_name="Lead",
        mode=mode,
        last_message_at=(last_message_at or datetime.now(UTC)).replace(tzinfo=None),
    )
    session.add(thread)
    await session.flush()
    return thread


@pytest.mark.asyncio
async def test_list_threads_orders_by_last_message_at(
    client: TestClient, session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    older = await _seed_thread(
        session,
        chat_jid="111@s.whatsapp.net",
        last_message_at=now - timedelta(hours=2),
    )
    newer = await _seed_thread(
        session,
        chat_jid="222@s.whatsapp.net",
        last_message_at=now,
    )
    await session.commit()

    resp = client.get("/whatsapp/threads")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    ids = [t["id"] for t in data["threads"]]
    assert ids == [str(newer.id), str(older.id)]


@pytest.mark.asyncio
async def test_list_threads_filters_by_mode(
    client: TestClient, session: AsyncSession
) -> None:
    await _seed_thread(session, chat_jid="111@s.whatsapp.net", mode=ThreadMode.BOT)
    await _seed_thread(session, chat_jid="222@s.whatsapp.net", mode=ThreadMode.HUMAN)
    await session.commit()

    resp = client.get("/whatsapp/threads", params={"mode": "human"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["threads"][0]["mode"] == "human"


@pytest.mark.asyncio
async def test_get_thread_returns_messages_chronological(
    client: TestClient, session: AsyncSession
) -> None:
    thread = await _seed_thread(session)
    session.add_all(
        [
            WhatsappMessage(
                message_id="M1",
                chat_jid=thread.chat_jid,
                from_jid=thread.chat_jid,
                text="first",
                wa_timestamp=1_700_000_000,
            ),
            WhatsappMessage(
                message_id="M2",
                chat_jid=thread.chat_jid,
                from_jid=thread.chat_jid,
                text="second",
                wa_timestamp=1_700_000_060,
            ),
        ]
    )
    await session.commit()

    resp = client.get(f"/whatsapp/threads/{thread.id}")
    assert resp.status_code == 200
    data = resp.json()
    texts = [m["text"] for m in data["messages"]]
    assert texts == ["first", "second"]


@pytest.mark.asyncio
async def test_get_thread_404_when_unknown(client: TestClient) -> None:
    resp = client.get("/whatsapp/threads/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_thread_takeover_then_release(
    client: TestClient, session: AsyncSession
) -> None:
    thread = await _seed_thread(session)
    await session.commit()

    take = client.patch(
        f"/whatsapp/threads/{thread.id}",
        json={"mode": "human", "takeover_reason": "manual"},
    )
    assert take.status_code == 200
    assert take.json()["mode"] == "human"
    assert take.json()["takeover_reason"] == "manual"

    release = client.patch(
        f"/whatsapp/threads/{thread.id}",
        json={"mode": "bot"},
    )
    assert release.status_code == 200
    assert release.json()["mode"] == "bot"
    assert release.json()["takeover_reason"] is None


@pytest.mark.asyncio
async def test_get_bot_config_creates_default_if_missing(
    client: TestClient,
) -> None:
    resp = client.get("/whatsapp/bot-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chatbot_enabled"] is False


@pytest.mark.asyncio
async def test_patch_bot_config_updates_fields(
    client: TestClient, session: AsyncSession
) -> None:
    resp = client.patch(
        "/whatsapp/bot-config",
        json={
            "chatbot_enabled": True,
            "greeting_en": "Hello there.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chatbot_enabled"] is True
    assert data["greeting_en"] == "Hello there."

    # Persisted in DB
    cfg = await session.get(BotConfig, "default")
    assert cfg is not None
    assert cfg.chatbot_enabled is True
    assert cfg.greeting_en == "Hello there."
