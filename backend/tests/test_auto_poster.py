"""Tests for the Phase 2 auto-poster module.

Covers the no-op path (daemon unconfigured), the no-group path, the
audience filtering (sale property -> SALE+BOTH groups, not RENT), and
the post-success status flip.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import respx
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.auto_poster import dispatch_slot
from shmuel_backend.config import settings as cfg
from shmuel_backend.enums import (
    BrokerFeeStatus,
    GroupAudience,
    GroupPlatform,
    PostSlotStatus,
    PropertyStatus,
    PropertyType,
)
from shmuel_backend.models import Group, PostSlot, Property

DAEMON_URL = "http://daemon.local:8787"


@pytest.fixture
def with_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "whatsapp_daemon_url", DAEMON_URL)
    monkeypatch.setattr(cfg, "whatsapp_daemon_token", "tok123")


async def _make_property(session: AsyncSession, *, prop_type: PropertyType) -> Property:
    prop = Property(
        type=prop_type,
        status=PropertyStatus.AVAILABLE,
        price=1_000_000,
        currency="ILS",
        rooms=3,
        neighborhood="Talbiya",
        broker_fee_status=BrokerFeeStatus.YES,
    )
    session.add(prop)
    await session.flush()
    return prop


async def _make_slot(session: AsyncSession, prop: Property) -> PostSlot:
    slot = PostSlot(
        property_id=prop.id,
        scheduled_for=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(slot)
    await session.flush()
    await session.refresh(slot, attribute_names=["property"])
    return slot


async def _make_group(
    session: AsyncSession,
    *,
    platform: GroupPlatform,
    audience: GroupAudience,
    target_url: str = "12345-67890@g.us",
    name: str = "G1",
    active: bool = True,
) -> Group:
    g = Group(
        name=name,
        platform=platform,
        audience=audience,
        target_url=target_url,
        active=active,
    )
    session.add(g)
    await session.flush()
    return g


@pytest.mark.asyncio
async def test_dispatch_skipped_when_daemon_unconfigured(session: AsyncSession) -> None:
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    result = await dispatch_slot(session, slot)
    assert result.skipped_reason == "whatsapp_daemon_unconfigured"
    assert result.attempted == 0
    assert slot.status == PostSlotStatus.PENDING


@pytest.mark.asyncio
async def test_dispatch_skipped_when_no_groups(
    session: AsyncSession, with_daemon: None,
) -> None:
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    result = await dispatch_slot(session, slot)
    assert result.skipped_reason == "no_matching_groups"
    assert result.attempted == 0


@pytest.mark.asyncio
async def test_dispatch_filters_groups_by_audience(
    session: AsyncSession, with_daemon: None,
) -> None:
    """A SALE property should not be posted to RENT-only groups."""
    prop = await _make_property(session, prop_type=PropertyType.SALE)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.RENT, name="RentOnly")
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.SALE, name="SaleOnly",
                      target_url="22222-22222@g.us")
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, name="Both",
                      target_url="33333-33333@g.us")
    await session.commit()

    with respx.mock(assert_all_called=False) as rmock:
        route = rmock.post(f"{DAEMON_URL}/send-group").mock(
            return_value=Response(200, json={"ok": True, "messageId": "X"}),
        )
        result = await dispatch_slot(session, slot)
    assert result.attempted == 2  # SaleOnly + Both
    assert result.succeeded == 2
    assert route.call_count == 2
    assert slot.status == PostSlotStatus.POSTED


@pytest.mark.asyncio
async def test_dispatch_skips_groups_with_no_target_url(
    session: AsyncSession, with_daemon: None,
) -> None:
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, target_url="", name="Empty")
    await session.commit()
    result = await dispatch_slot(session, slot)
    assert result.attempted == 1
    assert result.succeeded == 0
    assert result.group_failures == [{"group": "Empty", "error": "missing_target_url"}]
    assert slot.status == PostSlotStatus.PENDING


FAKE_PNG = b"\x89PNG-collage-bytes"
FAKE_JPEGS = [b"\xff\xd8-branded-1", b"\xff\xd8-branded-2"]


def _mock_share_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub render_share_pack with a collage + two branded photos, and zero
    the inter-image pacing delay so tests don't sleep."""
    from shmuel_backend.collage_service import SharePack

    async def fake_pack(_session: AsyncSession, _pid: object, **_kw: object) -> SharePack:
        return SharePack(collage_png=FAKE_PNG, photos=list(FAKE_JPEGS))

    monkeypatch.setattr("shmuel_backend.auto_poster.render_share_pack", fake_pack)
    monkeypatch.setattr("shmuel_backend.auto_poster._INTER_IMAGE_DELAY_S", 0)


@pytest.mark.asyncio
async def test_dispatch_sends_collage_then_branded_photos(
    session: AsyncSession, with_daemon: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a share pack renders, dispatch posts the captioned collage first,
    then each branded photo with no caption (not plain text)."""
    import base64
    import json

    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, target_url="55555-55555@g.us")
    await session.commit()

    _mock_share_pack(monkeypatch)

    with respx.mock(assert_all_called=False) as rmock:
        img_route = rmock.post(f"{DAEMON_URL}/send-group-image").mock(
            return_value=Response(200, json={"ok": True, "messageId": "IMG"}),
        )
        text_route = rmock.post(f"{DAEMON_URL}/send-group").mock(
            return_value=Response(200, json={"ok": True, "messageId": "TXT"}),
        )
        result = await dispatch_slot(session, slot)

    assert result.succeeded == 1
    assert img_route.call_count == 3  # collage + 2 branded photos
    assert text_route.call_count == 0

    bodies = [json.loads(c.request.content) for c in img_route.calls]
    assert all(b["groupId"] == "55555-55555@g.us" for b in bodies)
    assert base64.b64decode(bodies[0]["imageBase64"]) == FAKE_PNG
    assert bodies[0]["caption"]  # the post text rides along as the caption
    assert [base64.b64decode(b["imageBase64"]) for b in bodies[1:]] == FAKE_JPEGS
    assert all(b["caption"] == "" for b in bodies[1:])  # photos ride captionless
    assert result.photo_failures == 0
    assert result.group_failures == []
    assert slot.status == PostSlotStatus.POSTED


@pytest.mark.asyncio
async def test_dispatch_photo_failure_does_not_unsucceed_group(
    session: AsyncSession, with_daemon: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dropped branded-photo send is tallied in photo_failures but the group
    still counts: the collage + caption already landed and we won't
    double-post on retry. group_failures stays reserved for groups that did
    not get the post at all."""
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, target_url="66666-66666@g.us",
                      name="Flaky")
    await session.commit()

    _mock_share_pack(monkeypatch)

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(f"{DAEMON_URL}/send-group-image").mock(
            side_effect=[
                Response(200, json={"ok": True, "messageId": "IMG"}),  # collage
                Response(503, text="daemon hiccup"),                    # photo 1
                Response(200, json={"ok": True, "messageId": "IMG2"}),  # photo 2
            ],
        )
        result = await dispatch_slot(session, slot)

    assert result.attempted == 1
    assert result.succeeded == 1
    assert result.group_failures == []  # the group itself got the post
    assert result.photo_failures == 1
    assert slot.status == PostSlotStatus.POSTED


@pytest.mark.asyncio
async def test_dispatch_marks_posted_only_on_success(
    session: AsyncSession, with_daemon: None,
) -> None:
    """If the daemon rejects every send, the slot should stay PENDING for retry."""
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, target_url="44444-44444@g.us")
    await session.commit()

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(f"{DAEMON_URL}/send-group").mock(
            return_value=Response(503, text="daemon down"),
        )
        result = await dispatch_slot(session, slot)
    assert result.attempted == 1
    assert result.succeeded == 0
    assert slot.status == PostSlotStatus.PENDING
