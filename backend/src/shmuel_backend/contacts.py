"""Contacts CRM — minimal address book with segment tags.

CSV format: Phone, Name, Email, Language, Segments, Notes — UTF-8 with BOM
so Excel and third-party WhatsApp bulk-send tools render Hebrew correctly.
Segments are semicolon-separated within the single CSV cell to avoid
colliding with the comma delimiter.

Segment filter is *any-of* semantics: ?segment=buyer&segment=vip returns
contacts that have buyer OR vip (not both). Phase 1 keeps it simple; if we
need AND semantics later, add ?match=all without breaking the API.
"""
import csv
import io
import re
import uuid
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.models import Contact
from shmuel_backend.schemas import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

CSV_COLUMNS = ["Phone", "Name", "Email", "Language", "Segments", "Notes"]


def _normalize_phone(raw: str | None) -> str | None:
    """Strip everything that isn't a digit or leading +. Used for dedup
    matching so '+972 50-000-0000' and '+972500000000' compare equal."""
    if raw is None:
        return None
    cleaned = re.sub(r"[\s\-()]", "", raw.strip())
    return cleaned or None


def _split_segments(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.split(";") if s.strip()]


def _join_segments(segs: list[str] | None) -> str:
    return ";".join(segs or [])


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
                _join_segments(c.segments),
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


# ───────── CSV import ───────────────────────────────────────────────


class ImportRow(BaseModel):
    """Per-row preview / result for CSV import."""

    model_config = ConfigDict(extra="forbid")

    row_number: int  # 1-based, matches what users see in Excel
    name: str
    phone: str | None = None
    email: str | None = None
    language: str | None = None
    segments: list[str] = []
    notes: str | None = None
    status: str  # "create" | "duplicate" | "error" | "created"
    detail: str | None = None  # human reason for duplicate / error


class ImportSummary(BaseModel):
    total_rows: int
    would_create: int
    would_skip_duplicates: int
    errors: int


class ImportResult(BaseModel):
    summary: ImportSummary
    rows: list[ImportRow]


def _parse_csv(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """Decode + parse a CSV upload. Returns (rows, header) for downstream
    processing. Tolerant of: UTF-8 BOM, mixed casing in headers, extra cols.
    Raises HTTPException on hard parse failures."""
    # Strip BOM if present, decode as utf-8 (most common); fall back if needed
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not decode the file as UTF-8: {exc}",
            ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV has no header row.")

    # Normalize header names to lowercase for case-insensitive lookup
    rows = [
        {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        for row in reader
    ]
    return rows, [name.strip().lower() for name in reader.fieldnames]


def _validate_row(
    row_number: int, raw: dict[str, str], existing_phones: set[str]
) -> ImportRow:
    name = raw.get("name", "").strip()
    if not name:
        return ImportRow(
            row_number=row_number,
            name="",
            status="error",
            detail="Name is required.",
        )

    phone_raw = raw.get("phone") or None
    phone = _normalize_phone(phone_raw)

    parsed = ImportRow(
        row_number=row_number,
        name=name,
        phone=phone,
        email=raw.get("email") or None,
        language=raw.get("language") or None,
        segments=_split_segments(raw.get("segments")),
        notes=raw.get("notes") or None,
        status="create",
    )

    if phone and phone in existing_phones:
        parsed.status = "duplicate"
        parsed.detail = f"A contact with phone {phone} already exists."

    return parsed


@router.post("/import", response_model=ImportResult)
async def import_contacts_csv(
    session: SessionDep,
    file: UploadFile,
    dry_run: Annotated[bool, Query()] = True,
) -> ImportResult:
    """Parse a CSV upload and either preview the import (`dry_run=true`)
    or actually write the new contacts (`dry_run=false`).

    Dedup: skips rows whose phone matches any existing contact. Rows
    without a phone are always created. Rows with errors are skipped on
    apply but still surfaced in the preview so the user can fix the file
    and re-import.

    Returns per-row results so the admin UI can show a preview table.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    raw_rows, _headers = _parse_csv(content)

    # Pull all existing phones for dedup. Cheap (single broker, contacts
    # in the hundreds at most). For larger lists we'd batch-query.
    existing_rows = (
        await session.execute(select(Contact.phone))
    ).scalars().all()
    existing_phones = {
        normed
        for raw in existing_rows
        if (normed := _normalize_phone(raw)) is not None
    }

    # Track phones we've already seen in THIS import too, so two rows in
    # the same file with the same phone aren't both created.
    seen_in_batch: set[str] = set()
    parsed_rows: list[ImportRow] = []
    for i, raw in enumerate(raw_rows, start=2):  # row 1 is header
        parsed = _validate_row(i, raw, existing_phones | seen_in_batch)
        if parsed.status == "create" and parsed.phone:
            seen_in_batch.add(parsed.phone)
        parsed_rows.append(parsed)

    summary = ImportSummary(
        total_rows=len(parsed_rows),
        would_create=sum(1 for r in parsed_rows if r.status == "create"),
        would_skip_duplicates=sum(
            1 for r in parsed_rows if r.status == "duplicate"
        ),
        errors=sum(1 for r in parsed_rows if r.status == "error"),
    )

    if not dry_run:
        for row in parsed_rows:
            if row.status != "create":
                continue
            session.add(
                Contact(
                    name=row.name,
                    phone=row.phone,
                    email=row.email,
                    language=row.language,
                    segments=row.segments,
                    notes=row.notes,
                    source="csv-import",
                )
            )
            row.status = "created"
        await session.commit()

    return ImportResult(summary=summary, rows=parsed_rows)


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
