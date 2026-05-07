"""Newsletter subscription + digest dispatch.

Public endpoints (no auth, called from the WordPress signup form):
  POST   /public/newsletter/subscribe           — sign up, double opt-in
  GET    /public/newsletter/confirm/{token}     — click-through from email
  GET    /public/newsletter/unsubscribe/{token} — one-click unsubscribe

Admin endpoint (api-key gated by the global middleware):
  GET    /newsletter/subscribers                — list + stats for the admin

The digest trigger lives in `dispatch_digests_after_property` and is
called from properties.create_property after a new available row is
committed. We send when a subscriber's pending-property count for
their type filter crosses `settings.newsletter_digest_threshold`.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.email_client import send_email
from shmuel_backend.enums import (
    PropertyStatus,
    PropertyType,
    SubscriberPreference,
)
from shmuel_backend.models import CloudPhoto, NewsletterSubscriber, Property
from shmuel_backend.newsletter_compose import render_confirmation, render_digest

log = logging.getLogger(__name__)

public_router = APIRouter(prefix="/public/newsletter", tags=["newsletter-public"])
admin_router = APIRouter(prefix="/newsletter", tags=["newsletter"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# Pragmatic email regex — anything with a local-part, an @, a domain, and a
# TLD. Not RFC-perfect, and intentionally so: deliverability is the real test
# (the confirm email either lands or doesn't), and we don't want to bring in
# email-validator just for a friend-scale signup form.
_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SubscribeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    language: str = Field(default="en", pattern="^(en|he)$")
    type_filter: SubscriberPreference = SubscriberPreference.BOTH
    source: str | None = Field(default="wordpress", max_length=50)


class SubscribeResponse(BaseModel):
    """Always returns the same shape regardless of whether the row was new
    or already existed — we don't disclose which addresses are in our list."""

    status: str = "ok"


class SubscriberRead(BaseModel):
    id: uuid.UUID
    email: str
    language: str
    type_filter: SubscriberPreference
    confirmed_at: datetime | None = None
    unsubscribed_at: datetime | None = None
    last_digest_at: datetime | None = None
    source: str | None = None
    created_at: datetime


class SubscriberStats(BaseModel):
    total: int
    confirmed: int
    pending: int
    unsubscribed: int


class SubscriberListResponse(BaseModel):
    items: list[SubscriberRead]
    stats: SubscriberStats


def _new_token() -> str:
    return secrets.token_urlsafe(32)


@public_router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(payload: SubscribeRequest, session: SessionDep) -> SubscribeResponse:
    """Create or refresh a subscription and send the confirmation email.

    Idempotent on email: re-subscribing an already-confirmed address is a
    no-op (returns ok). A previously-unsubscribed address gets re-armed
    and a fresh confirmation email."""
    email_lower = payload.email.lower()
    existing = (
        await session.execute(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == email_lower)
        )
    ).scalar_one_or_none()

    if existing is None:
        sub = NewsletterSubscriber(
            email=email_lower,
            language=payload.language,
            type_filter=payload.type_filter,
            confirmation_token=_new_token(),
            unsubscribe_token=_new_token(),
            source=payload.source,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        rendered = render_confirmation(sub)
        await send_email(
            to=sub.email,
            subject=rendered.subject,
            html=rendered.html,
            text=rendered.text,
        )
        return SubscribeResponse()

    # Existing row: refresh language/preferences and resend the
    # confirmation email if not yet confirmed. If they had previously
    # unsubscribed, treat this as a fresh signup with new tokens.
    existing.language = payload.language
    existing.type_filter = payload.type_filter
    existing.source = payload.source
    if existing.unsubscribed_at is not None:
        existing.unsubscribed_at = None
        existing.confirmed_at = None
        existing.confirmation_token = _new_token()
        existing.unsubscribe_token = _new_token()
        existing.last_digest_at = None

    needs_confirmation = existing.confirmed_at is None
    await session.commit()
    await session.refresh(existing)

    if needs_confirmation:
        rendered = render_confirmation(existing)
        await send_email(
            to=existing.email,
            subject=rendered.subject,
            html=rendered.html,
            text=rendered.text,
        )
    return SubscribeResponse()


@public_router.get("/confirm/{token}", response_class=HTMLResponse)
async def confirm(token: str, session: SessionDep) -> HTMLResponse:
    sub = (
        await session.execute(
            select(NewsletterSubscriber).where(
                NewsletterSubscriber.confirmation_token == token
            )
        )
    ).scalar_one_or_none()
    if sub is None or sub.unsubscribed_at is not None:
        return HTMLResponse(_simple_page("This link is no longer valid."), status_code=404)
    if sub.confirmed_at is None:
        sub.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()
    msg_he = "ההרשמה אושרה. תודה!"
    msg_en = "You're confirmed. We'll send you new properties as they're listed."
    msg = msg_he if sub.language == "he" else msg_en
    return HTMLResponse(_simple_page(msg))


@public_router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, session: SessionDep) -> HTMLResponse:
    sub = (
        await session.execute(
            select(NewsletterSubscriber).where(
                NewsletterSubscriber.unsubscribe_token == token
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        return HTMLResponse(_simple_page("This link is no longer valid."), status_code=404)
    if sub.unsubscribed_at is None:
        sub.unsubscribed_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()
    msg_he = "ההרשמה בוטלה. לא נשלח עוד הודעות."
    msg_en = "You've been unsubscribed. We won't email you again."
    msg = msg_he if sub.language == "he" else msg_en
    return HTMLResponse(_simple_page(msg))


@admin_router.get("/subscribers", response_model=SubscriberListResponse)
async def list_subscribers(session: SessionDep) -> SubscriberListResponse:
    rows = list(
        (
            await session.execute(
                select(NewsletterSubscriber).order_by(
                    NewsletterSubscriber.created_at.desc()
                )
            )
        )
        .scalars()
        .all()
    )
    confirmed = sum(1 for r in rows if r.confirmed_at and r.unsubscribed_at is None)
    pending = sum(1 for r in rows if r.confirmed_at is None and r.unsubscribed_at is None)
    unsubscribed = sum(1 for r in rows if r.unsubscribed_at is not None)
    return SubscriberListResponse(
        items=[SubscriberRead.model_validate(r, from_attributes=True) for r in rows],
        stats=SubscriberStats(
            total=len(rows),
            confirmed=confirmed,
            pending=pending,
            unsubscribed=unsubscribed,
        ),
    )


@admin_router.delete(
    "/subscribers/{subscriber_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_subscriber(
    subscriber_id: uuid.UUID, session: SessionDep
) -> None:
    sub = await session.get(NewsletterSubscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="subscriber not found")
    await session.delete(sub)
    await session.commit()


# ---------------------------------------------------------------------------
# Digest dispatch
# ---------------------------------------------------------------------------


def _matching_property_filter(type_filter: SubscriberPreference):
    if type_filter == SubscriberPreference.RENT:
        return Property.type == PropertyType.RENT
    if type_filter == SubscriberPreference.SALE:
        return Property.type == PropertyType.SALE
    # BOTH
    return Property.type.in_([PropertyType.RENT, PropertyType.SALE])


async def dispatch_digests_after_property(
    session: AsyncSession, threshold: int
) -> int:
    """Send a digest to every confirmed subscriber whose unseen-property
    count meets `threshold`. Returns the number of emails actually sent
    (or attempted — the email_client treats unconfigured Resend as a no-op).

    Called from properties.create_property after the new row is committed.
    Failures inside this routine are logged and swallowed: a digest hiccup
    must never roll back the property write.
    """
    try:
        subs = list(
            (
                await session.execute(
                    select(NewsletterSubscriber).where(
                        NewsletterSubscriber.confirmed_at.is_not(None),
                        NewsletterSubscriber.unsubscribed_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    except Exception as exc:
        log.warning("Newsletter dispatch: failed to load subscribers: %s", exc, exc_info=True)
        return 0

    sent = 0
    for sub in subs:
        try:
            if await _maybe_send_digest(session, sub, threshold):
                sent += 1
        except Exception as exc:
            log.warning(
                "Newsletter dispatch failed for %s: %s",
                sub.email,
                exc,
                exc_info=True,
            )
    return sent


async def _maybe_send_digest(
    session: AsyncSession, sub: NewsletterSubscriber, threshold: int
) -> bool:
    type_clause = _matching_property_filter(sub.type_filter)
    base = select(Property).where(
        Property.status == PropertyStatus.AVAILABLE,
        type_clause,
    )
    if sub.last_digest_at is not None:
        base = base.where(Property.created_at > sub.last_digest_at)

    rows = list((await session.execute(base.order_by(Property.created_at.asc()))).scalars().all())
    if len(rows) < threshold:
        return False

    photos_by_property = await _photos_for(session, [p.id for p in rows])
    rendered = render_digest(sub, rows, photos_by_property)

    sub.last_digest_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()

    await send_email(
        to=sub.email,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
    )
    return True


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


def _simple_page(body: str) -> str:
    return f"""<!doctype html>
<html><head>
  <meta charset="utf-8" />
  <title>Classic Jerusalem Realty</title>
  <style>
    body {{ font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
            color: #222; max-width: 480px; margin: 80px auto; padding: 24px;
            text-align: center; }}
    p {{ font-size: 18px; line-height: 1.5; }}
    a {{ color: #17483b; }}
  </style>
</head>
<body>
  <p>{body}</p>
  <p><a href="{_site_link_target()}">classicjerusalem.com</a></p>
</body></html>"""


def _site_link_target() -> str:
    from shmuel_backend.config import settings as _s

    return _s.newsletter_site_base_url.rstrip("/")

# Stats helper used by main.py /system aggregator.
async def newsletter_counts(session: AsyncSession) -> dict[str, int]:
    total = (
        await session.execute(select(func.count()).select_from(NewsletterSubscriber))
    ).scalar_one()
    confirmed = (
        await session.execute(
            select(func.count())
            .select_from(NewsletterSubscriber)
            .where(
                NewsletterSubscriber.confirmed_at.is_not(None),
                NewsletterSubscriber.unsubscribed_at.is_(None),
            )
        )
    ).scalar_one()
    return {"total": int(total), "confirmed": int(confirmed)}
