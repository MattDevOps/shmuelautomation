"""Contacts CRM — minimal address book with segment tags.

CSV export shape (default): Phone, Name, Email, Language, Notes — UTF-8 with
BOM so Excel + webot's importer render Hebrew correctly.

Segment filter is *any-of* semantics: ?segment=buyer&segment=vip returns
contacts that have buyer OR vip (not both). Phase 1 keeps it simple; if we
need AND semantics later, add ?match=all without breaking the API.
"""
import csv
import io
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.models import Contact
from shmuel_backend.schemas import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

CSV_COLUMNS = ["Phone", "Name", "Email", "Language", "Notes"]


def _matches_any_segment(contact: Contact, wanted: list[str]) -> bool:
    if not wanted:
        return True
    contact_segments = contact.segments or []
    return any(s in contact_segments for s in wanted)


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    session: SessionDep,
    segment: Annotated[list[str] | None, Query()] = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Contact]:
    stmt = select(Contact)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Contact.name.ilike(like), Contact.phone.ilike(like))
        )
    stmt = stmt.order_by(Contact.created_at.desc())

    # Segment filter is applied in Python because JSON membership across both
    # Postgres and SQLite is awkward; the contact list is small (single broker).
    rows = list((await session.execute(stmt)).scalars().all())
    if segment:
        wanted = [s for s in segment if s]
        rows = [c for c in rows if _matches_any_segment(c, wanted)]

    return rows[offset : offset + limit]


@router.get("/segments", response_model=list[str])
async def list_segments(session: SessionDep) -> list[str]:
    """Distinct segment values across all contacts — for autocomplete."""
    result = await session.execute(select(Contact.segments))
    seen: set[str] = set()
    for row in result.scalars().all():
        for s in row or []:
            if isinstance(s, str) and s:
                seen.add(s)
    return sorted(seen)


@router.get("/export.csv")
async def export_contacts_csv(
    session: SessionDep,
    segment: Annotated[list[str] | None, Query()] = None,
) -> Response:
    stmt = select(Contact).order_by(Contact.created_at.desc())
    rows = list((await session.execute(stmt)).scalars().all())
    if segment:
        wanted = [s for s in segment if s]
        rows = [c for c in rows if _matches_any_segment(c, wanted)]

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    for c in rows:
        writer.writerow(
            [
                c.phone or "",
                c.name,
                c.email or "",
                c.language or "",
                (c.notes or "").replace("\n", " "),
            ]
        )
    body = "﻿" + buf.getvalue()  # UTF-8 BOM so Excel renders Hebrew

    filename = f"contacts-{date.today().isoformat()}.csv"
    if segment:
        slug = "-".join(s for s in segment if s)
        filename = f"contacts-{slug}-{date.today().isoformat()}.csv"

    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate, session: SessionDep
) -> Contact:
    contact = Contact(**payload.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(contact_id: uuid.UUID, session: SessionDep) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    return contact


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: uuid.UUID, payload: ContactUpdate, session: SessionDep
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID, session: SessionDep
) -> Response:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    await session.delete(contact)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
