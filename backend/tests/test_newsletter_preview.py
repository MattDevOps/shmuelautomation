"""Tests for the /newsletter/preview admin endpoint."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.enums import (
    BrokerFeeStatus,
    PropertyStatus,
    PropertyType,
)
from shmuel_backend.models import Property


async def _make_property(
    session: AsyncSession,
    *,
    type_: PropertyType,
    neighborhood: str = "Talbiya",
    price: Decimal = Decimal("8000"),
) -> Property:
    prop = Property(
        type=type_,
        status=PropertyStatus.AVAILABLE,
        price=price,
        currency="ILS",
        rooms=3,
        size_sqm=80,
        neighborhood=neighborhood,
        broker_fee_status=BrokerFeeStatus.YES,
        description="Spacious 3-room apartment in a quiet neighborhood.",
    )
    session.add(prop)
    await session.flush()
    return prop


@pytest.mark.asyncio
async def test_preview_empty_state(client: TestClient) -> None:
    resp = client.get("/newsletter/preview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "No available properties" in resp.text


@pytest.mark.asyncio
async def test_preview_renders_full_digest(
    client: TestClient, session: AsyncSession
) -> None:
    await _make_property(session, type_=PropertyType.RENT, neighborhood="Rehavia")
    await _make_property(session, type_=PropertyType.SALE, neighborhood="Baka",
                         price=Decimal("3000000"))
    await session.commit()

    resp = client.get("/newsletter/preview?language=en&type_filter=both")
    assert resp.status_code == 200
    assert "Classic Jerusalem Realty" in resp.text
    # Rent properties show in English
    assert "FOR RENT" in resp.text
    assert "FOR SALE" in resp.text
    assert "Rehavia" in resp.text
    assert "Baka" in resp.text


@pytest.mark.asyncio
async def test_preview_hebrew(client: TestClient, session: AsyncSession) -> None:
    await _make_property(session, type_=PropertyType.RENT)
    await session.commit()

    resp = client.get("/newsletter/preview?language=he")
    assert resp.status_code == 200
    assert 'dir="rtl"' in resp.text
    assert "להשכרה" in resp.text  # "For rent" in Hebrew


@pytest.mark.asyncio
async def test_preview_filters_by_type(client: TestClient, session: AsyncSession) -> None:
    await _make_property(session, type_=PropertyType.RENT, neighborhood="OnlyRent")
    await _make_property(session, type_=PropertyType.SALE, neighborhood="OnlySale")
    await session.commit()

    rent_only = client.get("/newsletter/preview?type_filter=rent")
    assert "OnlyRent" in rent_only.text
    assert "OnlySale" not in rent_only.text

    sale_only = client.get("/newsletter/preview?type_filter=sale")
    assert "OnlySale" in sale_only.text
    assert "OnlyRent" not in sale_only.text


@pytest.mark.asyncio
async def test_preview_validates_inputs(client: TestClient) -> None:
    assert client.get("/newsletter/preview?language=de").status_code == 422
    assert client.get("/newsletter/preview?type_filter=invalid").status_code == 422
    assert client.get("/newsletter/preview?limit=0").status_code == 422
    assert client.get("/newsletter/preview?limit=21").status_code == 422
