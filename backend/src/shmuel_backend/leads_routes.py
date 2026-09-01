"""Review queue for LLM-extracted leads.

Extractions never write straight into the address book — see
`lead_extraction` for why. These routes are the review step:

- `GET  /leads`                 — the queue, newest first, filterable by status
- `GET  /leads/{id}`            — one extraction
- `POST /leads/{id}/approve`    — create or update the Contact, mark approved
- `POST /leads/{id}/reject`     — mark rejected, write nothing to contacts
- `PATCH /leads/{id}`           — fix the extraction before approving it
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.enums import LeadSource, LeadStatus
from shmuel_backend.lead_extraction import approve_lead
from shmuel_backend.models import LeadExtraction

router = APIRouter(prefix="/leads", tags=["leads"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: LeadSource
    source_ref: str | None
    phone: str | None
    display_name: str | None
    summary: str | None
    requirements: dict[str, Any] | None
    status: LeadStatus
    contact_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class LeadList(BaseModel):
    items: list[LeadRead]
    total: int
    pending: int


class LeadUpdate(BaseModel):
    """Corrections Shmuel makes before approving.

    Every field optional — the admin sends only what it changed.
    """

    display_name: str | None = None
    phone: str | None = None
    summary: str | None = None
    requirements: dict[str, Any] | None = None


async def _get_lead(session: AsyncSession, lead_id: uuid.UUID) -> LeadExtraction:
    lead = await session.get(LeadExtraction, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@router.get("", response_model=LeadList)
async def list_leads(
    session: SessionDep,
    lead_status: Annotated[LeadStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadList:
    """The review queue. Defaults to everything; pass status=pending for the inbox."""
    stmt = select(LeadExtraction)
    count_stmt = select(func.count(LeadExtraction.id))
    if lead_status is not None:
        stmt = stmt.where(LeadExtraction.status == lead_status)
        count_stmt = count_stmt.where(LeadExtraction.status == lead_status)

    stmt = stmt.order_by(desc(LeadExtraction.created_at)).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    pending = (
        await session.execute(
            select(func.count(LeadExtraction.id)).where(
                LeadExtraction.status == LeadStatus.PENDING
            )
        )
    ).scalar_one()
    return LeadList(
        items=[LeadRead.model_validate(r) for r in rows],
        total=total,
        pending=pending,
    )


@router.get("/{lead_id}", response_model=LeadRead)
async def get_lead(lead_id: uuid.UUID, session: SessionDep) -> LeadExtraction:
    return await _get_lead(session, lead_id)


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: uuid.UUID, payload: LeadUpdate, session: SessionDep
) -> LeadExtraction:
    """Correct an extraction before approving it.

    Only pending leads are editable: once approved the Contact is the record
    of truth, and editing the extraction afterwards would silently disagree
    with it.
    """
    lead = await _get_lead(session, lead_id)
    if lead.status is not LeadStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only pending leads can be edited",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)
    await session.commit()
    await session.refresh(lead)
    return lead


class ApproveResult(BaseModel):
    lead: LeadRead
    contact_id: uuid.UUID


@router.post("/{lead_id}/approve", response_model=ApproveResult)
async def approve(lead_id: uuid.UUID, session: SessionDep) -> ApproveResult:
    """Write the lead into the address book.

    Re-approving an already-approved lead is a no-op rather than an error, so
    a double-click in the admin cannot duplicate a contact's notes.
    """
    lead = await _get_lead(session, lead_id)
    if lead.status is LeadStatus.APPROVED and lead.contact_id is not None:
        return ApproveResult(
            lead=LeadRead.model_validate(lead), contact_id=lead.contact_id
        )
    if lead.status is LeadStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="lead was rejected; edit it back to pending is not supported",
        )
    contact = await approve_lead(session, lead)
    await session.commit()
    await session.refresh(lead)
    return ApproveResult(lead=LeadRead.model_validate(lead), contact_id=contact.id)


@router.post("/{lead_id}/reject", response_model=LeadRead)
async def reject(lead_id: uuid.UUID, session: SessionDep) -> LeadExtraction:
    """Discard the extraction. Nothing is written to contacts."""
    lead = await _get_lead(session, lead_id)
    if lead.status is LeadStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="lead was already approved into a contact",
        )
    lead.status = LeadStatus.REJECTED
    lead.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    await session.refresh(lead)
    return lead
