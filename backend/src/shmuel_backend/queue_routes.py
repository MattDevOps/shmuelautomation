"""Post queue HTTP endpoints + auto-enqueue helpers.

The queue is purely declarative — we never auto-fire posts. The admin opens
the page, sees due slots, taps share for each. Slot lifecycle:

  pending → posted   (admin tapped share)
  pending → skipped  (admin chose to skip this property at this slot)
  pending → cancelled (property went rented/sold/deleted)
"""
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.collage_service import render_property_collage
from shmuel_backend.compose import (
    compose_post,
    facebook_share_url,
    whatsapp_share_url,
)
from shmuel_backend.db import get_session
from shmuel_backend.enums import PostSlotStatus
from shmuel_backend.models import CloudPhoto, PostSlot, Property
from shmuel_backend.scheduler import next_post_slot
from shmuel_backend.schemas import (
    PostCompose,
    PostSlotRead,
    PostSlotWithProperty,
)

router = APIRouter(prefix="/post-queue", tags=["queue"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _capacity_at(session: AsyncSession) -> dict[datetime, int]:
    """How many pending slots are already scheduled for each future slot start."""
    result = await session.execute(
        select(PostSlot.scheduled_for, func.count())
        .where(PostSlot.status == PostSlotStatus.PENDING)
        .group_by(PostSlot.scheduled_for)
    )
    out: dict[datetime, int] = {}
    for slot_dt, count in result.all():
        # SQLite returns naive datetimes; treat them as UTC.
        if slot_dt.tzinfo is None:
            slot_dt = slot_dt.replace(tzinfo=UTC)
        out[slot_dt] = int(count)
    return out


async def enqueue_property(
    session: AsyncSession,
    property_id: uuid.UUID,
    *,
    priority: int = 100,
    after: datetime | None = None,
) -> PostSlot:
    """Schedule the next post for this property. Caller commits.

    `after` defaults to now; pass the just-consumed slot's time when called
    from mark_posted/skip so the next slot lands strictly after, not on top
    of, the released slot.
    """
    capacity = await _capacity_at(session)
    floor = after or datetime.now(UTC)
    if floor.tzinfo is None:
        floor = floor.replace(tzinfo=UTC)
    when = next_post_slot(floor, capacity)
    slot = PostSlot(
        property_id=property_id,
        scheduled_for=when.replace(tzinfo=None),  # store naive UTC for SQLite portability
        status=PostSlotStatus.PENDING,
        priority=priority,
    )
    session.add(slot)
    return slot


async def cancel_pending_for(
    session: AsyncSession, property_id: uuid.UUID
) -> int:
    """Mark all pending slots for this property as cancelled. Caller commits."""
    result = await session.execute(
        select(PostSlot).where(
            PostSlot.property_id == property_id,
            PostSlot.status == PostSlotStatus.PENDING,
        )
    )
    cancelled = 0
    for slot in result.scalars().all():
        slot.status = PostSlotStatus.CANCELLED
        cancelled += 1
    return cancelled


@router.get("", response_model=list[PostSlotWithProperty])
async def list_queue(
    session: SessionDep,
    due_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PostSlotWithProperty]:
    stmt = (
        select(PostSlot, Property)
        .join(Property, PostSlot.property_id == Property.id)
        .where(PostSlot.status == PostSlotStatus.PENDING)
        .order_by(PostSlot.priority.desc(), PostSlot.scheduled_for.asc())
        .limit(limit)
    )
    if due_only:
        stmt = stmt.where(PostSlot.scheduled_for <= datetime.now(UTC).replace(tzinfo=None))

    rows = (await session.execute(stmt)).all()
    out: list[PostSlotWithProperty] = []
    for slot, prop in rows:
        out.append(
            PostSlotWithProperty(
                id=slot.id,
                property_id=slot.property_id,
                scheduled_for=slot.scheduled_for,
                status=slot.status,
                priority=slot.priority,
                posted_at=slot.posted_at,
                created_at=slot.created_at,
                property_type=prop.type,
                property_neighborhood=prop.neighborhood,
                property_address=prop.address,
                property_price=prop.price,
            )
        )
    return out


@router.patch("/{slot_id}/posted", response_model=PostSlotRead)
async def mark_posted(slot_id: uuid.UUID, session: SessionDep) -> PostSlot:
    slot = await session.get(PostSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    if slot.status != PostSlotStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"slot is already {slot.status.value}"
        )
    slot.status = PostSlotStatus.POSTED
    slot.posted_at = datetime.now(UTC).replace(tzinfo=None)
    # Roll the next slot for this property so the queue keeps flowing.
    await enqueue_property(session, slot.property_id, after=slot.scheduled_for)
    await session.commit()
    await session.refresh(slot)
    return slot


@router.patch("/{slot_id}/skip", response_model=PostSlotRead)
async def skip_slot(slot_id: uuid.UUID, session: SessionDep) -> PostSlot:
    slot = await session.get(PostSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    if slot.status != PostSlotStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"slot is already {slot.status.value}"
        )
    slot.status = PostSlotStatus.SKIPPED
    # Push the property to the next eligible slot strictly after this one.
    await enqueue_property(session, slot.property_id, after=slot.scheduled_for)
    await session.commit()
    await session.refresh(slot)
    return slot


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_slot(slot_id: uuid.UUID, session: SessionDep) -> Response:
    slot = await session.get(PostSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    if slot.status == PostSlotStatus.PENDING:
        slot.status = PostSlotStatus.CANCELLED
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Composition endpoint, lives on /properties/{id}/compose for clean URLs ──

compose_router = APIRouter(prefix="/properties", tags=["compose"])


@compose_router.get("/{property_id}/compose", response_model=PostCompose)
async def compose_property_post(
    property_id: uuid.UUID, session: SessionDep
) -> PostCompose:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")

    photos_result = await session.execute(
        select(CloudPhoto)
        .where(CloudPhoto.property_id == property_id)
        .order_by(CloudPhoto.created_at.asc())
    )
    photos = list(photos_result.scalars().all())

    text_en = compose_post(prop, lang="en", photos=photos)
    text_he = compose_post(prop, lang="he", photos=photos)
    return PostCompose(
        text_en=text_en,
        text_he=text_he,
        whatsapp_share_url=whatsapp_share_url(text_en),
        facebook_share_url=facebook_share_url(prop.yad2_url) if prop.yad2_url else None,
        has_collage=len(photos) > 0,
    )


@compose_router.get("/{property_id}/collage")
async def property_collage(property_id: uuid.UUID, session: SessionDep) -> Response:
    """Render the share collage (up to 4 photos + logo) as a PNG.

    This is the same image the WhatsApp auto-poster sends, so the admin can
    preview exactly what goes out. 404 when there are no photos / no Drive
    connection, which the UI shows as 'no collage yet'.
    """
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")
    png = await render_property_collage(session, property_id)
    if png is None:
        raise HTTPException(status_code=404, detail="no collage available")
    return Response(
        content=png,
        media_type="image/png",
        headers={"cache-control": "private, max-age=120"},
    )
