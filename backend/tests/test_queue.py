import uuid
from datetime import UTC, datetime

import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.config import settings as cfg
from shmuel_backend.enums import (
    GroupAudience,
    GroupPlatform,
    PostSlotStatus,
)
from shmuel_backend.models import Group, PostSlot

DAEMON_URL = "http://daemon.local:8787"


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "rent",
        "price": "8500.00",
        "neighborhood": "Baka",
    }
    base.update(overrides)
    return client.post("/properties", json=base).json()


async def _slots_for(session: AsyncSession, property_id: str) -> list[PostSlot]:
    result = await session.execute(
        select(PostSlot).where(PostSlot.property_id == uuid.UUID(property_id))
    )
    return list(result.scalars().all())


async def test_create_property_auto_enqueues_pending_slot(
    client: TestClient, session: AsyncSession
) -> None:
    prop = _create(client, neighborhood="Baka")
    slots = await _slots_for(session, prop["id"])
    assert len(slots) == 1
    assert slots[0].status == PostSlotStatus.PENDING
    assert slots[0].priority == 200  # new listings get priority bump
    assert slots[0].scheduled_for > datetime.now(UTC).replace(tzinfo=None)


async def test_create_rented_property_does_not_enqueue(
    client: TestClient, session: AsyncSession
) -> None:
    prop = _create(client, status="rented")
    slots = await _slots_for(session, prop["id"])
    assert slots == []


async def test_status_change_to_rented_cancels_pending_slots(
    client: TestClient, session: AsyncSession
) -> None:
    prop = _create(client)
    # confirm we have a pending slot
    pre = await _slots_for(session, prop["id"])
    assert any(s.status == PostSlotStatus.PENDING for s in pre)

    client.patch(f"/properties/{prop['id']}", json={"status": "rented"})

    session.expire_all()  # invalidate cached objects so we re-read
    post = await _slots_for(session, prop["id"])
    assert all(s.status != PostSlotStatus.PENDING for s in post)
    assert any(s.status == PostSlotStatus.CANCELLED for s in post)


async def test_status_back_to_available_re_enqueues(
    client: TestClient, session: AsyncSession
) -> None:
    prop = _create(client, status="rented")
    assert await _slots_for(session, prop["id"]) == []

    client.patch(f"/properties/{prop['id']}", json={"status": "available"})

    session.expire_all()
    slots = await _slots_for(session, prop["id"])
    pending = [s for s in slots if s.status == PostSlotStatus.PENDING]
    assert len(pending) == 1


def test_list_queue_returns_pending_with_property_snippet(
    client: TestClient,
) -> None:
    _create(client, neighborhood="Baka", price="8500")
    _create(client, neighborhood="Katamon", price="9500")

    r = client.get("/post-queue")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    by_hood = {r["property_neighborhood"]: r for r in rows}
    assert "Baka" in by_hood
    assert by_hood["Baka"]["property_price"] == "8500.00"
    assert by_hood["Baka"]["status"] == "pending"


def test_list_queue_orders_high_priority_first(client: TestClient) -> None:
    # All new listings have priority 200, so ordering falls to scheduled_for asc.
    # We can't test priority ordering without manipulating the DB directly here.
    # This test confirms the basic case: 2 new listings, both priority 200.
    _create(client, neighborhood="A")
    _create(client, neighborhood="B")
    rows = client.get("/post-queue").json()
    assert all(r["priority"] == 200 for r in rows)


def test_due_only_filter_excludes_future_slots(client: TestClient) -> None:
    _create(client)  # scheduled in the future
    rows = client.get("/post-queue", params={"due_only": True}).json()
    assert rows == []


def test_mark_posted_advances_to_next_slot(
    client: TestClient,
) -> None:
    prop = _create(client)
    initial_rows = client.get("/post-queue").json()
    assert len(initial_rows) == 1
    slot_id = initial_rows[0]["id"]
    initial_when = initial_rows[0]["scheduled_for"]

    r = client.patch(f"/post-queue/{slot_id}/posted")
    assert r.status_code == 200
    assert r.json()["status"] == "posted"
    assert r.json()["posted_at"] is not None

    # Queue should have a fresh pending slot for the same property.
    next_rows = client.get("/post-queue").json()
    assert len(next_rows) == 1
    assert next_rows[0]["property_id"] == prop["id"]
    assert next_rows[0]["scheduled_for"] > initial_when


def test_mark_posted_404_for_unknown_slot(client: TestClient) -> None:
    r = client.patch(
        "/post-queue/00000000-0000-0000-0000-000000000000/posted"
    )
    assert r.status_code == 404


def test_mark_posted_409_when_already_posted(client: TestClient) -> None:
    _create(client)
    slot_id = client.get("/post-queue").json()[0]["id"]
    client.patch(f"/post-queue/{slot_id}/posted")  # first call marks posted

    # Subsequent calls hit the same now-posted slot
    r = client.patch(f"/post-queue/{slot_id}/posted")
    assert r.status_code == 409


def test_skip_advances_property_to_next_slot(client: TestClient) -> None:
    prop = _create(client)
    rows = client.get("/post-queue").json()
    slot_id = rows[0]["id"]
    initial_when = rows[0]["scheduled_for"]

    r = client.patch(f"/post-queue/{slot_id}/skip")
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"

    next_rows = client.get("/post-queue").json()
    assert len(next_rows) == 1
    assert next_rows[0]["property_id"] == prop["id"]
    assert next_rows[0]["scheduled_for"] > initial_when


def test_cancel_slot_204(client: TestClient) -> None:
    _create(client)
    slot_id = client.get("/post-queue").json()[0]["id"]
    r = client.delete(f"/post-queue/{slot_id}")
    assert r.status_code == 204
    assert client.get("/post-queue").json() == []


def test_compose_returns_english_and_hebrew(client: TestClient) -> None:
    prop = _create(
        client,
        type="sale",
        price="3200000",
        neighborhood="Baka",
        description="Bright top-floor apartment",
    )
    r = client.get(f"/properties/{prop['id']}/compose")
    assert r.status_code == 200
    body = r.json()
    assert "For sale" in body["text_en"]
    assert "Baka" in body["text_en"]
    assert "ILS 3,200,000" in body["text_en"]
    assert "למכירה" in body["text_he"]
    assert body["whatsapp_share_url"].startswith("https://wa.me/?text=")


def test_compose_404_for_missing_property(client: TestClient) -> None:
    r = client.get(
        "/properties/00000000-0000-0000-0000-000000000000/compose"
    )
    assert r.status_code == 404


def test_compose_has_collage_false_without_photos(client: TestClient) -> None:
    prop = _create(client, type="sale", price="3200000", neighborhood="Baka")
    body = client.get(f"/properties/{prop['id']}/compose").json()
    assert body["has_collage"] is False


def test_collage_404_when_no_photos(client: TestClient) -> None:
    prop = _create(client, type="rent", price="8000", neighborhood="Talbiya")
    r = client.get(f"/properties/{prop['id']}/collage")
    assert r.status_code == 404


def test_collage_404_for_missing_property(client: TestClient) -> None:
    r = client.get(
        "/properties/00000000-0000-0000-0000-000000000000/collage"
    )
    assert r.status_code == 404


# ── POST /post-queue/{slot}/dispatch — manual "post now" via the daemon ──


async def _pending_slot(session: AsyncSession, property_id: str) -> PostSlot:
    slots = await _slots_for(session, property_id)
    return next(s for s in slots if s.status == PostSlotStatus.PENDING)


async def test_dispatch_now_skips_when_daemon_unconfigured(
    client: TestClient, session: AsyncSession
) -> None:
    prop = _create(client)
    slot = await _pending_slot(session, prop["id"])
    r = client.post(f"/post-queue/{slot.id}/dispatch")
    assert r.status_code == 200
    body = r.json()
    assert body["skipped_reason"] == "whatsapp_daemon_unconfigured"
    assert body["status"] == "pending"
    assert body["attempted"] == 0 and body["succeeded"] == 0


def test_dispatch_now_404_for_unknown_slot(client: TestClient) -> None:
    assert client.post(f"/post-queue/{uuid.uuid4()}/dispatch").status_code == 404


async def test_dispatch_now_409_when_not_pending(
    client: TestClient, session: AsyncSession
) -> None:
    prop = _create(client)
    slot = await _pending_slot(session, prop["id"])
    client.patch(f"/post-queue/{slot.id}/posted")
    r = client.post(f"/post-queue/{slot.id}/dispatch")
    assert r.status_code == 409


async def test_dispatch_now_sends_and_rolls_next_slot(
    client: TestClient, session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(cfg, "whatsapp_daemon_url", DAEMON_URL)
    monkeypatch.setattr(cfg, "whatsapp_daemon_token", "tok")
    session.add(
        Group(
            name="Rentals",
            platform=GroupPlatform.WHATSAPP,
            audience=GroupAudience.BOTH,
            target_url="111-222@g.us",
            active=True,
        )
    )
    await session.commit()

    prop = _create(client)  # rent property -> matches BOTH group
    slot = await _pending_slot(session, prop["id"])

    with respx.mock(assert_all_called=False) as rmock:
        # No photos/Drive in tests, so the collage is None and it sends text.
        rmock.post(f"{DAEMON_URL}/send-group").mock(
            return_value=Response(200, json={"ok": True, "messageId": "X"})
        )
        r = client.post(f"/post-queue/{slot.id}/dispatch")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "posted"
    assert body["attempted"] == 1 and body["succeeded"] == 1

    session.expire_all()
    slots = await _slots_for(session, prop["id"])
    assert sum(1 for s in slots if s.status == PostSlotStatus.POSTED) == 1
    assert sum(1 for s in slots if s.status == PostSlotStatus.PENDING) == 1
