import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.config import settings
from shmuel_backend.db import get_session
from shmuel_backend.enums import PropertyStatus, PropertyType
from shmuel_backend.excel import properties_to_xlsx
from shmuel_backend.models import CloudPhoto, Contact, Property
from shmuel_backend.newsletter import dispatch_digests_after_property
from shmuel_backend.queue_routes import cancel_pending_for, enqueue_property
from shmuel_backend.schemas import (
    BulkDeleteRequest,
    BulkResult,
    BulkStatusUpdate,
    ContactMatch,
    DuplicateMatch,
    PropertyCreate,
    PropertyPhotoSummary,
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
    await session.flush()  # so prop.id is populated for the post-slot FK
    # New listings go into the queue at higher priority so they post first.
    if prop.status == PropertyStatus.AVAILABLE:
        await enqueue_property(session, prop.id, priority=200)
    await session.commit()
    await session.refresh(prop)
    # Newsletter digest dispatch — only available listings count toward the
    # threshold, and the routine swallows its own errors so a delivery hiccup
    # never rolls back the property write.
    if prop.status == PropertyStatus.AVAILABLE:
        await dispatch_digests_after_property(
            session, threshold=settings.newsletter_digest_threshold
        )
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


def _normalize_address(value: str | None) -> str:
    """Lowercase and collapse whitespace so '12 Emek Refaim' matches '12  emek refaim'."""
    if not value:
        return ""
    return " ".join(value.lower().split())


@router.get("/duplicates", response_model=list[DuplicateMatch])
async def find_duplicates(
    session: SessionDep,
    neighborhood: Annotated[str, Query(min_length=1, max_length=200)],
    address: Annotated[str, Query(min_length=1, max_length=500)],
    exclude_id: uuid.UUID | None = None,
) -> list[Property]:
    """Look for existing properties at the same address.

    Match: exact-after-normalize on neighborhood, plus equal-or-substring
    match on address (handles "12 Emek Refaim" vs "12 Emek Refaim St").
    Both fields are required — neighborhood alone is too broad to warn on.
    """
    nh = neighborhood.strip().lower()
    addr = _normalize_address(address)
    if not nh or not addr:
        return []

    rows = (await session.execute(select(Property))).scalars().all()
    matches: list[Property] = []
    for p in rows:
        if exclude_id is not None and p.id == exclude_id:
            continue
        if not p.neighborhood or not p.address:
            continue
        if p.neighborhood.strip().lower() != nh:
            continue
        p_addr = _normalize_address(p.address)
        if p_addr == addr or p_addr.startswith(addr) or addr.startswith(p_addr):
            matches.append(p)
    matches.sort(key=lambda m: m.created_at, reverse=True)
    return matches


@router.post("/bulk/status", response_model=BulkResult)
async def bulk_update_status(
    payload: BulkStatusUpdate, session: SessionDep
) -> BulkResult:
    """Apply the same status to many properties at once.

    Reuses the same queue side-effects as the single-row PATCH:
    leaving 'available' cancels pending posts; entering 'available'
    enqueues a fresh slot. Missing ids are returned as `not_found`
    rather than raising — bulk operations are best-effort by design.
    """
    new_status = payload.status
    affected = 0
    not_found: list[uuid.UUID] = []
    for pid in payload.ids:
        prop = await session.get(Property, pid)
        if prop is None:
            not_found.append(pid)
            continue
        previous_status = prop.status
        prop.status = new_status
        if previous_status == PropertyStatus.AVAILABLE and new_status != PropertyStatus.AVAILABLE:
            await cancel_pending_for(session, prop.id)
        elif previous_status != PropertyStatus.AVAILABLE and new_status == PropertyStatus.AVAILABLE:
            await enqueue_property(session, prop.id)
        affected += 1
    await session.commit()
    return BulkResult(affected=affected, not_found=not_found)


@router.post("/bulk/delete", response_model=BulkResult)
async def bulk_delete(
    payload: BulkDeleteRequest, session: SessionDep
) -> BulkResult:
    affected = 0
    not_found: list[uuid.UUID] = []
    for pid in payload.ids:
        prop = await session.get(Property, pid)
        if prop is None:
            not_found.append(pid)
            continue
        await session.delete(prop)
        affected += 1
    await session.commit()
    return BulkResult(affected=affected, not_found=not_found)


@router.get("/photo-summaries", response_model=list[PropertyPhotoSummary])
async def list_photo_summaries(session: SessionDep) -> list[PropertyPhotoSummary]:
    """One row per property that has at least one photo, with count + first thumb.

    Used by the properties listing page to render a thumbnail next to each
    row without an N+1 fetch. Properties with zero photos are simply absent.
    """
    counts_q = select(
        CloudPhoto.property_id,
        func.count(CloudPhoto.id).label("count"),
    ).group_by(CloudPhoto.property_id)
    counts = {
        row.property_id: row.count
        for row in (await session.execute(counts_q)).all()
    }
    if not counts:
        return []

    first_q = (
        select(
            CloudPhoto.property_id,
            CloudPhoto.thumbnail_url,
            CloudPhoto.web_view_url,
        )
        .order_by(CloudPhoto.property_id, CloudPhoto.created_at.desc())
        .distinct(CloudPhoto.property_id)
    )
    first_thumbs: dict[uuid.UUID, str | None] = {
        row.property_id: row.thumbnail_url or row.web_view_url
        for row in (await session.execute(first_q)).all()
    }
    return [
        PropertyPhotoSummary(
            property_id=pid,
            count=counts[pid],
            first_thumbnail=first_thumbs.get(pid),
        )
        for pid in counts
    ]


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
    previous_status = prop.status
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    # When a property leaves the available pool, cancel any pending posts;
    # when it returns to available, queue a fresh slot.
    if previous_status == PropertyStatus.AVAILABLE and prop.status != PropertyStatus.AVAILABLE:
        await cancel_pending_for(session, prop.id)
    elif previous_status != PropertyStatus.AVAILABLE and prop.status == PropertyStatus.AVAILABLE:
        await enqueue_property(session, prop.id)
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


@router.get(
    "/{property_id}/matching-contacts", response_model=list[ContactMatch]
)
async def matching_contacts(
    property_id: uuid.UUID, session: SessionDep
) -> list[ContactMatch]:
    """Surface contacts likely interested in this property.

    Match logic (case-insensitive on segment values):
    - audience-intent: 'buyer' for sale properties, 'renter' for rentals
    - neighborhood: any segment matching the property's neighborhood

    A contact scores 2 if they match both, 1 if just one. Sort by score
    desc, then name asc. Returns top 20 — Shmuel's brain is the limit
    on how many he can actually reach out to.
    """
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")

    audience = "buyer" if prop.type == PropertyType.SALE else "renter"
    neighborhood = (prop.neighborhood or "").strip().lower()

    rows = (await session.execute(select(Contact))).scalars().all()
    matches: list[ContactMatch] = []
    for c in rows:
        segs = [s.lower() for s in (c.segments or []) if isinstance(s, str)]
        score = 0
        reasons: list[str] = []
        if audience in segs:
            score += 1
            reasons.append(audience)
        if neighborhood and neighborhood in segs:
            score += 1
            reasons.append(prop.neighborhood or neighborhood)
        if score == 0:
            continue
        matches.append(
            ContactMatch(
                id=c.id,
                name=c.name,
                phone=c.phone,
                email=c.email,
                segments=list(c.segments or []),
                match_score=score,
                match_reasons=reasons,
            )
        )

    matches.sort(key=lambda m: (-m.match_score, m.name.lower()))
    return matches[:20]
