"""Timeline notes attached to a property.

Each note is one dated entry — "called landlord", "showing 4pm",
"price reduced to 3.1M". Distinct from `Property.notes` which is a
single static text blob describing the property itself.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.models import Property, PropertyNote
from shmuel_backend.schemas import PropertyNoteCreate, PropertyNoteRead

router = APIRouter(prefix="/properties", tags=["property-notes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/{property_id}/notes", response_model=list[PropertyNoteRead]
)
async def list_notes(
    property_id: uuid.UUID, session: SessionDep
) -> list[PropertyNote]:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")
    rows = (
        await session.execute(
            select(PropertyNote)
            .where(PropertyNote.property_id == property_id)
            .order_by(PropertyNote.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/{property_id}/notes",
    response_model=PropertyNoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    property_id: uuid.UUID,
    payload: PropertyNoteCreate,
    session: SessionDep,
) -> PropertyNote:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")
    note = PropertyNote(property_id=property_id, body=payload.body)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.delete(
    "/{property_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_note(
    property_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
) -> Response:
    note = await session.get(PropertyNote, note_id)
    if note is None or note.property_id != property_id:
        raise HTTPException(status_code=404, detail="note not found")
    await session.delete(note)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
