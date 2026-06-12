"""Tests for the /properties/photo-summaries endpoint used by the list page."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.enums import BrokerFeeStatus, PropertyStatus, PropertyType
from shmuel_backend.models import CloudPhoto, Property


async def _make_property(session: AsyncSession) -> Property:
    prop = Property(
        type=PropertyType.RENT,
        status=PropertyStatus.AVAILABLE,
        price=Decimal("8000"),
        currency="ILS",
        rooms=3,
        size_sqm=80,
        neighborhood="Talbiya",
        broker_fee_status=BrokerFeeStatus.YES,
        description="Spacious 3-room apartment.",
    )
    session.add(prop)
    await session.flush()
    return prop


def _add_photo(session: AsyncSession, prop: Property, name: str) -> CloudPhoto:
    photo = CloudPhoto(
        property_id=prop.id,
        provider="google_drive",
        external_id=f"drive-{name}",
        folder_external_id="folder-1",
        file_name=name,
        mime_type="image/jpeg",
        size_bytes=1234,
        checksum=f"sum-{name}",
        # A stale Drive thumbnailLink — the endpoint must NOT echo this back as
        # the thing the UI renders; the UI builds a fresh-thumbnail URL instead.
        thumbnail_url="https://lh3.googleusercontent.com/expired",
        web_view_url="https://drive.google.com/file/d/x/view",
    )
    session.add(photo)
    return photo


@pytest.mark.asyncio
async def test_photo_summary_exposes_first_photo_id(
    client: TestClient, session: AsyncSession
) -> None:
    prop = await _make_property(session)
    _add_photo(session, prop, "a.jpg")
    _add_photo(session, prop, "b.jpg")
    await session.commit()

    r = client.get("/properties/photo-summaries")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    summary = body[0]
    assert summary["property_id"] == str(prop.id)
    assert summary["count"] == 2
    # The list page needs a concrete photo id to build the fresh-thumbnail URL.
    assert summary["first_photo_id"] is not None


@pytest.mark.asyncio
async def test_photo_summary_empty_when_no_photos(client: TestClient) -> None:
    r = client.get("/properties/photo-summaries")
    assert r.status_code == 200
    assert r.json() == []
