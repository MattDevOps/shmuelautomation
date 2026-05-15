"""Tests for the webot WhatsApp client + admin status route.

Covers the graceful-no-op path (token unset) and the happy/sad HTTP paths
via respx. The real api.webot.co.il is never hit.
"""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from shmuel_backend import webot_client
from shmuel_backend.config import settings as cfg


@pytest.mark.asyncio
async def test_send_message_noop_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "")
    monkeypatch.setattr(cfg, "webot_from_phone", "")
    result = await webot_client.send_message(to_phone_number="972500000000", message="hi")
    assert result is None


@pytest.mark.asyncio
async def test_send_message_noop_when_from_phone_missing(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok123")
    monkeypatch.setattr(cfg, "webot_from_phone", "")
    result = await webot_client.send_message(to_phone_number="972500000000", message="hi")
    assert result is None


@pytest.mark.asyncio
async def test_send_message_posts_expected_body(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok123")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    with respx.mock(assert_all_called=False) as rmock:
        route = rmock.post("https://api.webot.co.il/api/v1/sendMessage").mock(
            return_value=Response(200, json={"ok": True})
        )
        result = await webot_client.send_message(
            to_phone_number="972527485568",
            message="New listing in Talbiya!",
            media_link="https://cdn.example.com/listing.jpg",
        )
    assert result == {"ok": True}
    assert route.called
    sent = route.calls[0].request
    # Bearer header carries the token alongside the body token (webot
    # accepts either; we send both to match the OpenAPI examples).
    assert sent.headers["authorization"] == "Bearer tok123"
    body = sent.read()
    assert b'"token":"tok123"' in body.replace(b" ", b"")
    assert b'"fromPhoneNumber":"972559662779"' in body.replace(b" ", b"")
    assert b'"toPhoneNumber":"972527485568"' in body.replace(b" ", b"")
    assert b'"mediaLink":' in body


@pytest.mark.asyncio
async def test_send_message_swallows_http_400(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok123")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post("https://api.webot.co.il/api/v1/sendMessage").mock(
            return_value=Response(400, text="bad token")
        )
        result = await webot_client.send_message(to_phone_number="972500000000", message="x")
    assert result is None


@pytest.mark.asyncio
async def test_get_groups_handles_list_response(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok123")
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post("https://api.webot.co.il/api/v1/getGroups").mock(
            return_value=Response(200, json=[{"id": "g1", "name": "Group 1"}])
        )
        result = await webot_client.get_groups()
    assert result == [{"id": "g1", "name": "Group 1"}]


@pytest.mark.asyncio
async def test_get_groups_handles_wrapped_response(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok123")
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post("https://api.webot.co.il/api/v1/getGroups").mock(
            return_value=Response(200, json={"groups": [{"id": "g2"}]})
        )
        result = await webot_client.get_groups()
    assert result == [{"id": "g2"}]


@pytest.mark.asyncio
async def test_webot_status_endpoint_unconfigured(client, monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "")
    monkeypatch.setattr(cfg, "webot_from_phone", "")
    resp = client.get("/webot/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"configured": False, "from_phone": None, "reachable": False, "detail": None}


@pytest.mark.asyncio
async def test_webot_status_endpoint_reachable(client, monkeypatch) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok123")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    with respx.mock(assert_all_called=False) as rmock:
        rmock.post("https://api.webot.co.il/api/v1/checkStatus").mock(
            return_value=Response(200, json={"connected": True})
        )
        resp = client.get("/webot/status")
    body = resp.json()
    assert body["configured"] is True
    assert body["from_phone"] == "972559662779"
    assert body["reachable"] is True
    assert body["detail"] == {"connected": True}
