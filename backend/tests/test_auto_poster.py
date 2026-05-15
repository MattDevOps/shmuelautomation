"""Tests for the Phase 2 auto-poster module.

Covers the no-op path (webot unconfigured), the no-group path, the
audience filtering (sale property → SALE+BOTH groups, not RENT), and
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
    # Eager-load the relationship so dispatch_slot sees slot.property
    await session.refresh(slot, attribute_names=["property"])
    return slot


async def _make_group(
    session: AsyncSession,
    *,
    platform: GroupPlatform,
    audience: GroupAudience,
    target_url: str = "972500000001",
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
async def test_dispatch_skipped_when_webot_unconfigured(session: AsyncSession) -> None:
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    result = await dispatch_slot(session, slot)
    assert result.skipped_reason == "webot_unconfigured"
    assert result.attempted == 0
    assert slot.status == PostSlotStatus.PENDING


@pytest.mark.asyncio
async def test_dispatch_skipped_when_no_groups(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(cfg, "webot_api_token", "tok")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    result = await dispatch_slot(session, slot)
    assert result.skipped_reason == "no_matching_groups"
    assert result.attempted == 0


@pytest.mark.asyncio
async def test_dispatch_filters_groups_by_audience(
    session: AsyncSession, monkeypatch
) -> None:
    """A SALE property should not be posted to RENT-only groups."""
    monkeypatch.setattr(cfg, "webot_api_token", "tok")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    prop = await _make_property(session, prop_type=PropertyType.SALE)
    slot = await _make_slot(session, prop)
    # Rent-only group should be skipped:
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.RENT, name="RentOnly")
    # Sale-only group + a BOTH-audience group should both be hit:
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.SALE, name="SaleOnly",
                      target_url="972500000002")
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, name="Both",
                      target_url="972500000003")
    await session.commit()

    with respx.mock(assert_all_called=False) as rmock:
        route = rmock.post("https://api.webot.co.il/api/v1/sendMessage").mock(
            return_value=Response(200, json={"ok": True})
        )
        result = await dispatch_slot(session, slot)
    assert result.attempted == 2  # SaleOnly + Both
    assert result.succeeded == 2
    assert route.call_count == 2
    assert slot.status == PostSlotStatus.POSTED


@pytest.mark.asyncio
async def test_dispatch_skips_groups_with_no_target_url(
    session: AsyncSession, monkeypatch
) -> None:
    """A misconfigured group (no target_url) is recorded as a failure but
    doesn't crash the dispatch."""
    monkeypatch.setattr(cfg, "webot_api_token", "tok")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, target_url="", name="Empty")
    await session.commit()
    result = await dispatch_slot(session, slot)
    assert result.attempted == 1
    assert result.succeeded == 0
    assert result.group_failures == [{"group": "Empty", "error": "missing_target_url"}]
    # Slot stays PENDING because no group succeeded.
    assert slot.status == PostSlotStatus.PENDING


@pytest.mark.asyncio
async def test_dispatch_marks_posted_only_on_success(
    session: AsyncSession, monkeypatch
) -> None:
    """If webot rejects every send, the slot should stay PENDING for retry."""
    monkeypatch.setattr(cfg, "webot_api_token", "tok")
    monkeypatch.setattr(cfg, "webot_from_phone", "972559662779")
    prop = await _make_property(session, prop_type=PropertyType.RENT)
    slot = await _make_slot(session, prop)
    await _make_group(session, platform=GroupPlatform.WHATSAPP,
                      audience=GroupAudience.BOTH, target_url="972500000001")
    await session.commit()

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post("https://api.webot.co.il/api/v1/sendMessage").mock(
            return_value=Response(503, text="webot down")
        )
        result = await dispatch_slot(session, slot)
    assert result.attempted == 1
    assert result.succeeded == 0
    assert slot.status == PostSlotStatus.PENDING
