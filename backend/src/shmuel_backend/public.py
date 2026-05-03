"""Public, unauthenticated read API for the WordPress site to consume.

Strict subset of fields — no owner PII (phone, name), no internal notes, no
broker-fee terms. Defaults to status=available; status filter is intentionally
not exposed to the public so rented/sold inventory can't be enumerated.

Cache-Control: public, max-age=60 — WordPress can safely cache for a minute.
"""
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.enums import PropertyStatus, PropertyType
from shmuel_backend.models import CloudPhoto, Property
from shmuel_backend.schemas import (
    PublicPhoto,
    PublicProperty,
    PublicPropertyList,
)

router = APIRouter(prefix="/public", tags=["public"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

CACHE_HEADER = "public, max-age=60"


def _to_public(prop: Property, photos: list[CloudPhoto]) -> PublicProperty:
    return PublicProperty(
        id=prop.id,
        type=prop.type,
        status=prop.status,
        price=prop.price,
        currency=prop.currency,
        rooms=prop.rooms,
        size_sqm=prop.size_sqm,
        floor=prop.floor,
        address=prop.address,
        neighborhood=prop.neighborhood,
        city=prop.city,
        description=prop.description,
        yad2_url=prop.yad2_url,
        photos=[
            PublicPhoto(
                thumbnail_url=p.thumbnail_url,
                web_view_url=p.web_view_url,
                file_name=p.file_name,
            )
            for p in photos
        ],
        created_at=prop.created_at,
        updated_at=prop.updated_at,
    )


async def _photos_for(
    session: AsyncSession, property_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[CloudPhoto]]:
    if not property_ids:
        return {}
    result = await session.execute(
        select(CloudPhoto)
        .where(CloudPhoto.property_id.in_(property_ids))
        .order_by(CloudPhoto.created_at.asc())
    )
    out: dict[uuid.UUID, list[CloudPhoto]] = {pid: [] for pid in property_ids}
    for photo in result.scalars().all():
        out[photo.property_id].append(photo)
    return out


@router.get("/properties", response_model=PublicPropertyList)
async def list_public_properties(
    session: SessionDep,
    response: Response,
    type: PropertyType | None = None,
    neighborhood: str | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PublicPropertyList:
    base = select(Property).where(Property.status == PropertyStatus.AVAILABLE)
    if type is not None:
        base = base.where(Property.type == type)
    if neighborhood is not None:
        base = base.where(Property.neighborhood == neighborhood)
    if min_price is not None:
        base = base.where(Property.price >= min_price)
    if max_price is not None:
        base = base.where(Property.price <= max_price)

    total_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(total_stmt)).scalar_one()

    page_stmt = (
        base.order_by(Property.created_at.desc()).limit(limit).offset(offset)
    )
    props = list((await session.execute(page_stmt)).scalars().all())
    photos_by_property = await _photos_for(session, [p.id for p in props])

    response.headers["cache-control"] = CACHE_HEADER
    return PublicPropertyList(
        items=[_to_public(p, photos_by_property.get(p.id, [])) for p in props],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/properties/{property_id}", response_model=PublicProperty)
async def get_public_property(
    property_id: uuid.UUID, session: SessionDep, response: Response
) -> PublicProperty:
    prop = await session.get(Property, property_id)
    if prop is None or prop.status != PropertyStatus.AVAILABLE:
        raise HTTPException(status_code=404, detail="property not found")
    photos = (await _photos_for(session, [prop.id])).get(prop.id, [])
    response.headers["cache-control"] = CACHE_HEADER
    return _to_public(prop, photos)
