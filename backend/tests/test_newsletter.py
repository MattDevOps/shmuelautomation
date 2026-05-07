"""Newsletter signup, confirm, unsubscribe, and digest dispatch."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient

from shmuel_backend.config import settings


def _property_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "rent",
        "price": "8500.00",
        "rooms": "3.5",
        "size_sqm": 80,
        "neighborhood": "Baka",
        "broker_fee_status": "yes",
    }
    base.update(overrides)
    return base


def _subscribe(
    client: TestClient,
    email: str = "alice@example.com",
    *,
    type_filter: str = "both",
    language: str = "en",
) -> dict[str, Any]:
    r = client.post(
        "/public/newsletter/subscribe",
        json={"email": email, "type_filter": type_filter, "language": language},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def resend_mock() -> Iterator[respx.MockRouter]:
    """Capture outgoing Resend HTTP calls when RESEND_API_KEY is set."""
    with respx.mock(base_url="https://api.resend.com", assert_all_called=False) as router:
        route = router.post("/emails", name="resend_send")
        route.respond(200, json={"id": "test-message-id"})
        yield router


@pytest.fixture
def with_resend_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")


def test_subscribe_creates_pending_subscriber(client: TestClient) -> None:
    body = _subscribe(client)
    assert body == {"status": "ok"}

    listing = client.get("/newsletter/subscribers").json()
    assert listing["stats"] == {
        "total": 1,
        "confirmed": 0,
        "pending": 1,
        "unsubscribed": 0,
    }
    item = listing["items"][0]
    assert item["email"] == "alice@example.com"
    assert item["confirmed_at"] is None


def test_subscribe_resend_emits_email_when_configured(
    client: TestClient, resend_mock: respx.MockRouter, with_resend_key: None
) -> None:
    _subscribe(client, "bob@example.com")
    sent = resend_mock["resend_send"]
    assert sent.called, "expected a Resend POST when RESEND_API_KEY is set"
    payload = sent.calls.last.request.content.decode("utf-8")
    assert "bob@example.com" in payload
    assert "Confirm" in payload  # subject line


def test_subscribe_no_op_when_resend_unconfigured(
    client: TestClient, resend_mock: respx.MockRouter
) -> None:
    """No RESEND_API_KEY = subscribe still records, no HTTP call goes out."""
    _subscribe(client, "carol@example.com")
    assert not resend_mock["resend_send"].called


def test_subscribe_is_idempotent_for_pending(client: TestClient) -> None:
    _subscribe(client, "dave@example.com", type_filter="rent")
    _subscribe(client, "dave@example.com", type_filter="sale")
    listing = client.get("/newsletter/subscribers").json()
    assert listing["stats"]["total"] == 1
    assert listing["items"][0]["type_filter"] == "sale"


def test_confirm_marks_subscriber_active(client: TestClient) -> None:
    _subscribe(client, "eve@example.com")
    token = _confirmation_token(client, "eve@example.com")

    r = client.get(f"/public/newsletter/confirm/{token}")
    assert r.status_code == 200
    assert "confirmed" in r.text.lower() or "אישור" in r.text

    listing = client.get("/newsletter/subscribers").json()
    assert listing["stats"]["confirmed"] == 1
    assert listing["items"][0]["confirmed_at"] is not None


def test_confirm_with_unknown_token_404s(client: TestClient) -> None:
    r = client.get("/public/newsletter/confirm/totally-bogus-token")
    assert r.status_code == 404


def _fetch_tokens(client: TestClient, email: str) -> tuple[str, str]:
    """Pull (confirmation_token, unsubscribe_token) directly from the DB.

    The admin listing endpoint deliberately doesn't expose tokens, so for
    tests that need to drive the click-through flow we go straight to the
    row via the same session the TestClient is already using.
    """
    from sqlalchemy import select

    from shmuel_backend.db import get_session
    from shmuel_backend.main import app
    from shmuel_backend.models import NewsletterSubscriber

    override = app.dependency_overrides[get_session]

    async def fetch() -> tuple[str, str]:
        async for s in override():
            row = (
                await s.execute(
                    select(NewsletterSubscriber).where(
                        NewsletterSubscriber.email == email
                    )
                )
            ).scalar_one()
            return row.confirmation_token, row.unsubscribe_token
        raise AssertionError("no session yielded")

    import asyncio

    return asyncio.get_event_loop().run_until_complete(fetch())


def _confirmation_token(client: TestClient, email: str) -> str:
    return _fetch_tokens(client, email)[0]


def _confirm_subscriber(client: TestClient, email: str) -> str:
    """Helper: subscribe + confirm + return the unsubscribe token."""
    _subscribe(client, email)
    confirm_token, unsub_token = _fetch_tokens(client, email)
    client.get(f"/public/newsletter/confirm/{confirm_token}")
    return unsub_token


def test_unsubscribe_marks_subscriber_unsubscribed(client: TestClient) -> None:
    token = _confirm_subscriber(client, "frank@example.com")
    r = client.get(f"/public/newsletter/unsubscribe/{token}")
    assert r.status_code == 200

    listing = client.get("/newsletter/subscribers").json()
    assert listing["stats"]["unsubscribed"] == 1


def test_resubscribe_after_unsubscribe_resets_state(client: TestClient) -> None:
    token = _confirm_subscriber(client, "grace@example.com")
    client.get(f"/public/newsletter/unsubscribe/{token}")
    _subscribe(client, "grace@example.com")
    listing = client.get("/newsletter/subscribers").json()
    assert listing["stats"]["total"] == 1
    assert listing["stats"]["pending"] == 1  # back to needing confirmation
    assert listing["stats"]["unsubscribed"] == 0


def test_digest_fires_when_threshold_met(
    client: TestClient,
    resend_mock: respx.MockRouter,
    with_resend_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "newsletter_digest_threshold", 3)
    _confirm_subscriber(client, "henry@example.com")
    resend_mock["resend_send"].reset()

    # 1st and 2nd properties — below threshold, no digest yet.
    client.post("/properties", json=_property_payload(price="8000"))
    client.post("/properties", json=_property_payload(price="9000"))
    assert resend_mock["resend_send"].call_count == 0

    # 3rd property triggers the digest.
    client.post("/properties", json=_property_payload(price="10000"))
    assert resend_mock["resend_send"].call_count == 1
    sent = resend_mock["resend_send"].calls.last.request.content.decode("utf-8")
    assert "henry@example.com" in sent
    assert "3 new properties" in sent or "3 נכסים" in sent


def test_digest_respects_type_filter(
    client: TestClient,
    resend_mock: respx.MockRouter,
    with_resend_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "newsletter_digest_threshold", 2)
    # Two subscribers: rent-only and sale-only — set the preference at signup
    # (we resubscribe to overwrite it after confirmation, since the unconfirmed
    # path keeps the row but updates the preference).
    _subscribe(client, "rent-fan@example.com", type_filter="rent")
    _subscribe(client, "sale-fan@example.com", type_filter="sale")
    # Confirm both.
    rent_confirm = _confirmation_token(client, "rent-fan@example.com")
    sale_confirm = _confirmation_token(client, "sale-fan@example.com")
    client.get(f"/public/newsletter/confirm/{rent_confirm}")
    client.get(f"/public/newsletter/confirm/{sale_confirm}")

    resend_mock["resend_send"].reset()

    # Two rentals: rent-fan should get a digest, sale-fan shouldn't.
    client.post("/properties", json=_property_payload(type="rent", price="8000"))
    client.post("/properties", json=_property_payload(type="rent", price="9000"))
    sent_to = [
        c.request.content.decode("utf-8")
        for c in resend_mock["resend_send"].calls
    ]
    assert any("rent-fan@example.com" in body for body in sent_to)
    assert not any("sale-fan@example.com" in body for body in sent_to)


def test_digest_skips_unconfirmed_and_unsubscribed(
    client: TestClient,
    resend_mock: respx.MockRouter,
    with_resend_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "newsletter_digest_threshold", 1)
    # Pending (unconfirmed) and confirmed-then-unsubscribed should both skip.
    _subscribe(client, "pending@example.com")
    unsub_token = _confirm_subscriber(client, "gone@example.com")
    client.get(f"/public/newsletter/unsubscribe/{unsub_token}")

    resend_mock["resend_send"].reset()
    client.post("/properties", json=_property_payload(price="8000"))
    sent_to = [
        c.request.content.decode("utf-8")
        for c in resend_mock["resend_send"].calls
    ]
    assert not any("pending@example.com" in body for body in sent_to)
    assert not any("gone@example.com" in body for body in sent_to)


def test_subscribe_rejects_obvious_garbage(client: TestClient) -> None:
    r = client.post(
        "/public/newsletter/subscribe",
        json={"email": "not-an-email"},
    )
    assert r.status_code == 422


def test_delete_subscriber(client: TestClient) -> None:
    _subscribe(client, "to-delete@example.com")
    listing = client.get("/newsletter/subscribers").json()
    sub_id = listing["items"][0]["id"]
    r = client.delete(f"/newsletter/subscribers/{sub_id}")
    assert r.status_code == 204
    assert client.get("/newsletter/subscribers").json()["stats"]["total"] == 0
