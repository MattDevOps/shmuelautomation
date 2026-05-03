import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.enums import PropertyStatus, PropertyType
from shmuel_backend.excel import properties_to_xlsx
from shmuel_backend.models import Property
from shmuel_backend.schemas import (
    PropertyCreate,
    PropertyRead,
    PropertyUpdate,
    Yad2ImportPreview,
    Yad2ImportRequest,
)
from shmuel_backend.yad2 import (
    Yad2Error,
    fetch_yad2_html,
    is_yad2_url,
    parse_yad2_html,
)

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

router = APIRouter(prefix="/properties", tags=["properties"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[PropertyRead])
async def list_properties(
    session: SessionDep,
    type: PropertyType | None = None,
    status: PropertyStatus | None = None,
    neighborhood: str | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Property]:
    stmt = select(Property)
    if type is not None:
        stmt = stmt.where(Property.type == type)
    if status is not None:
        stmt = stmt.where(Property.status == status)
    if neighborhood is not None:
        stmt = stmt.where(Property.neighborhood == neighborhood)
    if min_price is not None:
        stmt = stmt.where(Property.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Property.price <= max_price)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Property.address.ilike(like),
                Property.description.ilike(like),
                Property.neighborhood.ilike(like),
            )
        )
    stmt = stmt.order_by(Property.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
async def create_property(payload: PropertyCreate, session: SessionDep) -> Property:
    prop = Property(**payload.model_dump())
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return prop


@router.post("/import/yad2", response_model=Yad2ImportPreview)
async def import_from_yad2(payload: Yad2ImportRequest) -> Yad2ImportPreview:
    if not is_yad2_url(payload.url):
        raise HTTPException(status_code=400, detail="Not a yad2.co.il URL")
    try:
        html = await fetch_yad2_html(payload.url)
    except (Yad2Error, httpx.HTTPError) as exc:
        return Yad2ImportPreview(
            url=payload.url,
            warnings=[
                f"Could not load the page ({exc}). Fill in the form manually."
            ],
        )
    preview = parse_yad2_html(payload.url, html)
    return Yad2ImportPreview(**preview.__dict__)


@router.get("/export")
async def export_properties(session: SessionDep) -> Response:
    result = await session.execute(
        select(Property).order_by(Property.created_at.desc())
    )
    rows = list(result.scalars().all())
    body = properties_to_xlsx(rows)
    filename = f"properties-{date.today().isoformat()}.xlsx"
    return Response(
        content=body,
        media_type=XLSX_MEDIA_TYPE,
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{property_id}", response_model=PropertyRead)
async def get_property(property_id: uuid.UUID, session: SessionDep) -> Property:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")
    return prop


@router.patch("/{property_id}", response_model=PropertyRead)
async def update_property(
    property_id: uuid.UUID, payload: PropertyUpdate, session: SessionDep
) -> Property:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await session.commit()
    await session.refresh(prop)
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(property_id: uuid.UUID, session: SessionDep) -> Response:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")
    await session.delete(prop)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
