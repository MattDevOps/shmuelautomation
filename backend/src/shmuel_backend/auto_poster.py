"""Auto-posting for queued post slots via the WhatsApp daemon (Phase 2).

Wires the scheduler/queue into the Baileys-based whatsapp-daemon for
fully automated delivery to all active WhatsApp groups whose `audience`
matches the property's rent/sale type. Until WHATSAPP_DAEMON_URL +
WHATSAPP_DAEMON_TOKEN are set, dispatch is a no-op and the admin queue
keeps using the manual one-tap share flow.

`dispatch_slot()` is the unit-testable entry point. It's called from
the scheduler's tick on each due slot.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import whatsapp_client
from shmuel_backend.compose import compose_post
from shmuel_backend.config import settings
from shmuel_backend.enums import (
    GroupAudience,
    GroupPlatform,
    PostSlotStatus,
    PropertyType,
)
from shmuel_backend.models import CloudPhoto, Group, PostSlot, Property

log = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Outcome of attempting to send a slot to all matching groups.

    `attempted` counts groups we tried to reach; `succeeded` counts the
    ones the daemon accepted. A partial failure (some groups OK, some
    failed) is NOT enough to flip the slot to POSTED — caller decides
    whether to mark it POSTED or leave it for retry.
    """

    slot_id: str
    attempted: int = 0
    succeeded: int = 0
    skipped_reason: str | None = None
    group_failures: list[dict[str, str]] = field(default_factory=list)


def _audience_for_property(prop: Property) -> GroupAudience:
    """Map a property's type to the group audience filter.

    A short-term/long-term/Pesach rental matches RENT-audience groups.
    A sale property matches SALE-audience groups. BOTH matches everything.
    """
    if prop.type == PropertyType.SALE:
        return GroupAudience.SALE
    return GroupAudience.RENT


async def _active_target_groups(
    session: AsyncSession,
    *,
    platform: GroupPlatform,
    audience: GroupAudience,
) -> list[Group]:
    """Active groups on `platform` that accept either `audience` or BOTH."""
    rows = await session.execute(
        select(Group)
        .where(
            Group.active.is_(True),
            Group.platform == platform,
            Group.audience.in_([audience, GroupAudience.BOTH]),
        )
        .order_by(Group.sort_order.asc())
    )
    return list(rows.scalars().all())


def _build_message(prop: Property, photos: list[CloudPhoto]) -> str:
    """Hebrew message for Jerusalem WhatsApp groups.

    The frontend rebuild's i18n shows the same listing in 4 languages
    but our WhatsApp audience is Jerusalem-local, so HE is the right
    default. Override per-group if/when Shmuel wants multi-language
    sends.
    """
    return compose_post(prop, lang="he", photos=photos)


def _first_photo_url(photos: list[CloudPhoto]) -> str | None:
    """Pick the lead photo for the WhatsApp media attachment."""
    for p in photos:
        if p.thumbnail_url:
            return p.thumbnail_url
        if p.web_view_url:
            return p.web_view_url
    return None


async def dispatch_slot(
    session: AsyncSession,
    slot: PostSlot,
    *,
    mark_posted_on_success: bool = True,
) -> DispatchResult:
    """Send `slot`'s property to every active matching WhatsApp group.

    Returns a `DispatchResult` describing what happened. When the
    whatsapp-daemon is not configured, returns immediately with
    `skipped_reason="whatsapp_daemon_unconfigured"` so the caller can
    decide whether to fall back to the manual one-tap share flow.

    Idempotency: the caller controls whether to flip the slot's status.
    By default, ANY success marks the slot POSTED — partial failures are
    acceptable since the daemon occasionally drops sends and we don't
    want duplicate posts on retry. Set `mark_posted_on_success=False` to
    keep the slot in PENDING for caller-driven retry logic.
    """
    result = DispatchResult(slot_id=str(slot.id))

    if not settings.whatsapp_daemon_url or not settings.whatsapp_daemon_token:
        result.skipped_reason = "whatsapp_daemon_unconfigured"
        log.info("auto_poster: slot %s skipped — whatsapp daemon unconfigured", slot.id)
        return result

    prop = slot.property
    if prop is None:
        # Defensive — slots always join through to a property in normal flows.
        result.skipped_reason = "no_property"
        return result

    audience = _audience_for_property(prop)
    groups = await _active_target_groups(
        session,
        platform=GroupPlatform.WHATSAPP,
        audience=audience,
    )
    if not groups:
        result.skipped_reason = "no_matching_groups"
        log.info(
            "auto_poster: slot %s — no active whatsapp groups for audience=%s",
            slot.id, audience.value,
        )
        return result

    # Fetch photos once; reuse the lead photo URL for every group send.
    photos_rows = await session.execute(
        select(CloudPhoto).where(CloudPhoto.property_id == prop.id).order_by(CloudPhoto.created_at)
    )
    photos = list(photos_rows.scalars().all())
    message = _build_message(prop, photos)
    # Lead photo URL is captured but not yet sent — the Baileys daemon's
    # /send-group only accepts text today. Wire media-with-text once the
    # daemon learns to upload images (next iteration).
    _ = _first_photo_url(photos)

    for group in groups:
        result.attempted += 1
        # `target_url` on the Group row holds the WhatsApp group JID (e.g.
        # `12345-67890@g.us`) or bare id. Admin populates it from the
        # daemon's GET /groups list rather than free-form paste.
        to = group.target_url or ""
        if not to:
            result.group_failures.append({"group": group.name, "error": "missing_target_url"})
            continue
        sent = await whatsapp_client.send_to_group(
            group_id=to,
            message=message,
        )
        if sent is None:
            result.group_failures.append({"group": group.name, "error": "daemon_failure"})
            continue
        result.succeeded += 1

    if mark_posted_on_success and result.succeeded > 0:
        from datetime import UTC, datetime

        slot.status = PostSlotStatus.POSTED
        slot.posted_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

    log.info(
        "auto_poster: slot %s — attempted=%d succeeded=%d failures=%d skipped=%s",
        slot.id, result.attempted, result.succeeded,
        len(result.group_failures), result.skipped_reason,
    )
    return result
