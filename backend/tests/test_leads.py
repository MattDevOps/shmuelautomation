"""Lead extraction review queue.

The behaviour that matters here is that nothing reaches the address book
without a human approving it, and that the obvious admin mishaps —
double-clicking approve, approving then rejecting — cannot corrupt contacts.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.enums import LeadSource, LeadStatus
from shmuel_backend.lead_extraction import (
    _clean_requirements,
    format_notes,
    has_content,
)
from shmuel_backend.models import LeadExtraction


async def _make_lead(session: AsyncSession, **over) -> LeadExtraction:
    """Seed a pending extraction through the same session the app is using."""
    lead = LeadExtraction(
        source=over.get("source", LeadSource.CALL),
        source_ref=over.get("source_ref", "call-1"),
        phone=over.get("phone", "972501234567"),
        display_name=over.get("display_name", "Dana"),
        summary=over.get("summary", "Wants a 3 bedroom in City Center."),
        requirements=over.get(
            "requirements",
            {
                "deal_type": "rent",
                "rooms": "3 bedrooms",
                "neighborhoods": ["City Center"],
                "furnished": "unfurnished",
                "parking": True,
                "household": "family of 6",
                "timing": "asap",
            },
        ),
        status=LeadStatus.PENDING,
    )
    session.add(lead)
    await session.commit()
    return lead


def _contact_rows(client: TestClient) -> list[dict]:
    body = client.get("/contacts").json()
    return body["items"] if isinstance(body, dict) else body


def test_clean_requirements_drops_unknowns() -> None:
    """Nulls and empties must not survive — an empty extraction should look empty."""
    cleaned = _clean_requirements(
        {
            "rooms": "3 bedrooms",
            "neighborhoods": [],
            "budget": None,
            "parking": False,
            "furnished": "",
            "nonsense": "ignored",
        }
    )
    assert cleaned == {"rooms": "3 bedrooms", "parking": False}


def test_clean_requirements_tolerates_garbage() -> None:
    assert _clean_requirements(None) == {}
    assert _clean_requirements("not a dict") == {}


def test_has_content_rejects_empty_conversation() -> None:
    assert has_content({}, "") is False
    assert has_content({}, "  ") is False
    assert has_content({"rooms": "3"}, "") is True
    assert has_content({}, "Wants to view Tuesday") is True


def test_format_notes_is_readable() -> None:
    lead = LeadExtraction(
        source=LeadSource.CALL,
        summary="Wants a 3 bedroom in City Center.",
        requirements={
            "rooms": "3 bedrooms",
            "neighborhoods": ["City Center", "Rehavia"],
            "parking": True,
            "other": ["ground floor"],
        },
    )
    notes = format_notes(lead)
    assert "Wants a 3 bedroom in City Center." in notes
    assert "Rooms: 3 bedrooms" in notes
    assert "Neighbourhoods: City Center, Rehavia" in notes
    # Booleans must read as words, not Python repr.
    assert "Parking: yes" in notes
    assert "True" not in notes
    assert "Also wants: ground floor" in notes
    assert "phone call" in notes


@pytest.mark.asyncio
async def test_queue_lists_pending(session: AsyncSession, client: TestClient) -> None:
    await _make_lead(session)
    r = client.get("/leads", params={"status": "pending"})
    assert r.status_code == 200
    body = r.json()
    assert body["pending"] == 1
    assert body["items"][0]["requirements"]["rooms"] == "3 bedrooms"


@pytest.mark.asyncio
async def test_approve_creates_contact_with_notes(
    session: AsyncSession, client: TestClient
) -> None:
    lead_id = (await _make_lead(session)).id

    r = client.post(f"/leads/{lead_id}/approve")
    assert r.status_code == 200
    contact_id = r.json()["contact_id"]
    assert r.json()["lead"]["status"] == "approved"

    rows = _contact_rows(client)
    match = [c for c in rows if c["id"] == contact_id]
    assert len(match) == 1
    assert match[0]["phone"] == "972501234567"
    assert "3 bedrooms" in (match[0]["notes"] or "")


@pytest.mark.asyncio
async def test_approve_is_idempotent(
    session: AsyncSession, client: TestClient
) -> None:
    """A double-click in the admin must not duplicate the contact or its notes."""
    lead_id = (await _make_lead(session)).id
    first = client.post(f"/leads/{lead_id}/approve").json()
    second = client.post(f"/leads/{lead_id}/approve").json()
    assert first["contact_id"] == second["contact_id"]

    rows = _contact_rows(client)
    match = [c for c in rows if c["id"] == first["contact_id"]]
    assert len(match) == 1
    # The notes body must appear once, not twice.
    assert (match[0]["notes"] or "").count("Rooms: 3 bedrooms") == 1


@pytest.mark.asyncio
async def test_reject_writes_no_contact(
    session: AsyncSession, client: TestClient
) -> None:
    lead_id = (await _make_lead(session)).id
    before_rows = _contact_rows(client)

    r = client.post(f"/leads/{lead_id}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    after_rows = _contact_rows(client)
    assert len(after_rows) == len(before_rows)


@pytest.mark.asyncio
async def test_cannot_reject_after_approving(
    session: AsyncSession, client: TestClient
) -> None:
    lead_id = (await _make_lead(session)).id
    client.post(f"/leads/{lead_id}/approve")
    r = client.post(f"/leads/{lead_id}/reject")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_edit_before_approving(
    session: AsyncSession, client: TestClient
) -> None:
    """Shmuel fixes a mis-heard number, then approves — the fix must stick."""
    lead_id = (await _make_lead(session)).id
    r = client.patch(
        f"/leads/{lead_id}",
        json={"phone": "972509999999", "display_name": "Dana Levi"},
    )
    assert r.status_code == 200
    assert r.json()["phone"] == "972509999999"

    approved = client.post(f"/leads/{lead_id}/approve").json()
    rows = _contact_rows(client)
    match = [c for c in rows if c["id"] == approved["contact_id"]]
    assert match[0]["phone"] == "972509999999"
    assert match[0]["name"] == "Dana Levi"


@pytest.mark.asyncio
async def test_cannot_edit_after_approving(
    session: AsyncSession, client: TestClient
) -> None:
    lead_id = (await _make_lead(session)).id
    client.post(f"/leads/{lead_id}/approve")
    r = client.patch(f"/leads/{lead_id}", json={"summary": "changed"})
    assert r.status_code == 409
