"""Tests for the whatsapp_client + admin/webhook routes.

Covers:
- whatsapp_client functions no-op when daemon unconfigured
- whatsapp_client posts the right payloads + headers to the daemon
- /whatsapp/status reports configured/reachable correctly
- /whatsapp/session/blob PUT + GET round-trip (with X-Daemon-Token)
- /webhooks/whatsapp/inbound writes a message row and is idempotent on retry
- daemon-token check rejects calls missing the header
"""
from __future__ import annotations

import json

import pytest
import respx
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import whatsapp_client
from shmuel_backend.config import settings as cfg
from shmuel_backend.models import WhatsappMessage, WhatsappSession

DAEMON_URL = "http://daemon.local:8787"
TOKEN = "tok-123"


@pytest.fixture
def with_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "whatsapp_daemon_url", DAEMON_URL)
    monkeypatch.setattr(cfg, "whatsapp_daemon_token", TOKEN)


# ---------- whatsapp_client ----------------------------------------

@pytest.mark.asyncio
async def test_client_send_noop_when_unconfigured() -> None:
    result = await whatsapp_client.send_to_group(group_id="g@g.us", message="hi")
    assert result is None


@pytest.mark.asyncio
async def test_client_send_to_group_posts_expected(with_daemon: None) -> None:
    with respx.mock(assert_all_called=False) as rmock:
        route = rmock.post(f"{DAEMON_URL}/send-group").mock(
            return_value=Response(200, json={"ok": True, "messageId": "ABC"}),
        )
        result = await whatsapp_client.send_to_group(
            group_id="12345-67890@g.us", message="New listing!",
        )
    assert result == {"ok": True, "messageId": "ABC"}
    assert route.called
    req = route.calls[0].request
    assert req.headers["x-daemon-token"] == TOKEN
    parsed = json.loads(req.read())
    assert parsed == {"groupId": "12345-67890@g.us", "message": "New listing!"}


@pytest.mark.asyncio
async def test_client_send_to_phone_posts_expected(with_daemon: None) -> None:
    with respx.mock(assert_all_called=False) as rmock:
        route = rmock.post(f"{DAEMON_URL}/send-dm").mock(
            return_value=Response(200, json={"ok": True, "messageId": "Z"}),
        )
        result = await whatsapp_client.send_to_phone(
            to_phone_number="972527485568", message="hi",
        )
    assert result == {"ok": True, "messageId": "Z"}
    parsed = json.loads(route.calls[0].request.read())
    assert parsed == {"toPhone": "972527485568", "message": "hi"}


@pytest.mark.asyncio
async def test_client_check_status_returns_snapshot(with_daemon: None) -> None:
    snap = {"state": "connected", "phone": "972527485568", "qr": None}
    with respx.mock(assert_all_called=False) as rmock:
        rmock.get(f"{DAEMON_URL}/status").mock(return_value=Response(200, json=snap))
        result = await whatsapp_client.check_status()
    assert result == snap


@pytest.mark.asyncio
async def test_client_list_groups_unwraps_envelope(with_daemon: None) -> None:
    with respx.mock(assert_all_called=False) as rmock:
        rmock.get(f"{DAEMON_URL}/groups").mock(
            return_value=Response(200, json={"groups": [{"id": "g1@g.us", "subject": "G1"}]}),
        )
        result = await whatsapp_client.list_groups()
    assert result == [{"id": "g1@g.us", "subject": "G1"}]


# ---------- /whatsapp admin routes ----------------------------------

def test_admin_status_unconfigured(client) -> None:
    resp = client.get("/whatsapp/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["reachable"] is False


def test_admin_status_reachable(client, with_daemon: None) -> None:
    snap = {"state": "connected", "phone": "972527485568",
            "lastConnectedAt": "2026-05-16T10:00:00Z", "lastDisconnectReason": None,
            "qr": None}
    with respx.mock(assert_all_called=False) as rmock:
        rmock.get(f"{DAEMON_URL}/status").mock(return_value=Response(200, json=snap))
        resp = client.get("/whatsapp/status")
    body = resp.json()
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["connection_state"] == "connected"
    assert body["paired_phone"] == "972527485568"


def test_admin_status_unreachable_returns_configured_but_not_reachable(
    client, with_daemon: None,
) -> None:
    with respx.mock(assert_all_called=False) as rmock:
        rmock.get(f"{DAEMON_URL}/status").mock(return_value=Response(503))
        resp = client.get("/whatsapp/status")
    body = resp.json()
    assert body["configured"] is True
    assert body["reachable"] is False


# ---------- session blob round-trip --------------------------------

def test_session_blob_get_404_when_missing(client, with_daemon: None) -> None:
    resp = client.get("/whatsapp/session/blob", headers={"X-Daemon-Token": TOKEN})
    assert resp.status_code == 404


def test_session_blob_put_then_get(client, with_daemon: None) -> None:
    headers = {"X-Daemon-Token": TOKEN}
    resp = client.put(
        "/whatsapp/session/blob",
        headers=headers,
        json={"blob": "deadbeef"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    resp = client.get("/whatsapp/session/blob", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"blob": "deadbeef"}


def test_session_blob_put_overwrites_existing(client, with_daemon: None) -> None:
    headers = {"X-Daemon-Token": TOKEN}
    client.put("/whatsapp/session/blob", headers=headers, json={"blob": "v1"})
    client.put("/whatsapp/session/blob", headers=headers, json={"blob": "v2"})
    resp = client.get("/whatsapp/session/blob", headers=headers)
    assert resp.json() == {"blob": "v2"}


def test_session_blob_requires_token_when_configured(client, with_daemon: None) -> None:
    resp = client.put("/whatsapp/session/blob", json={"blob": "x"})
    assert resp.status_code == 401


def test_session_blob_skips_token_check_when_unconfigured(client) -> None:
    # No `with_daemon` -> token check is bypassed for local-dev convenience.
    # The route is still gated by the existing X-API-Key middleware on prod.
    resp = client.put("/whatsapp/session/blob", json={"blob": "x"})
    assert resp.status_code == 200


# ---------- inbound webhook ----------------------------------------

INBOUND_PAYLOAD = {
    "messageId": "ABCD1234",
    "fromJid": "972527485568@s.whatsapp.net",
    "fromPhone": "972527485568",
    "fromName": "Yossi",
    "chatJid": "972527485568@s.whatsapp.net",
    "isGroup": False,
    "groupId": None,
    "groupName": None,
    "text": "Do you have anything in Talbiya?",
    "mediaType": None,
    "timestamp": 1714234567,
}


@pytest.mark.asyncio
async def test_inbound_writes_message_row(
    client, with_daemon: None, session: AsyncSession,
) -> None:
    headers = {"X-Daemon-Token": TOKEN}
    resp = client.post("/webhooks/whatsapp/inbound", headers=headers, json=INBOUND_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"

    rows = (await session.execute(select(WhatsappMessage))).scalars().all()
    assert len(rows) == 1
    assert rows[0].message_id == "ABCD1234"
    assert rows[0].text == "Do you have anything in Talbiya?"
    assert rows[0].from_phone == "972527485568"
    assert rows[0].is_group is False


@pytest.mark.asyncio
async def test_inbound_is_idempotent_on_retry(
    client, with_daemon: None, session: AsyncSession,
) -> None:
    headers = {"X-Daemon-Token": TOKEN}
    r1 = client.post("/webhooks/whatsapp/inbound", headers=headers, json=INBOUND_PAYLOAD)
    r2 = client.post("/webhooks/whatsapp/inbound", headers=headers, json=INBOUND_PAYLOAD)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"
    rows = (await session.execute(select(WhatsappMessage))).scalars().all()
    assert len(rows) == 1


def test_inbound_rejects_missing_token(client, with_daemon: None) -> None:
    resp = client.post("/webhooks/whatsapp/inbound", json=INBOUND_PAYLOAD)
    assert resp.status_code == 401


def test_inbound_skips_messages_without_id(client, with_daemon: None) -> None:
    payload = {**INBOUND_PAYLOAD, "messageId": None}
    resp = client.post(
        "/webhooks/whatsapp/inbound",
        headers={"X-Daemon-Token": TOKEN},
        json=payload,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_session_round_trip_persists_row(
    client, with_daemon: None, session: AsyncSession,
) -> None:
    """Sanity: the PUT actually inserts a WhatsappSession row."""
    client.put(
        "/whatsapp/session/blob",
        headers={"X-Daemon-Token": TOKEN},
        json={"blob": "abc"},
    )
    rows = (await session.execute(select(WhatsappSession))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == "default"
    assert rows[0].blob == "abc"
