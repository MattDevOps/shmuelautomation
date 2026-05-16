"""Auto-posting for queued post slots via webot (Phase 2).

Wires the scheduler/queue into webot WhatsApp delivery. Today the
admin dashboard's queue shows pending slots and Shmuel taps "share"
to fire the OS-native share sheet. With this module, once
WEBOT_API_TOKEN + WEBOT_FROM_PHONE are set in the Cloud Run secrets,
slots can be dispatched directly to webot for fully automated delivery
to all active WhatsApp groups whose `audience` matches the property's
rent/sale type.

Currently this module exists but is NOT yet wired into the scheduler
tick. Wiring decisions still need Shmuel input:
  - Auto-post on slot trigger, or queue-and-confirm with one-tap approval?
  - Post to all active groups, or per-group rules (e.g. status updates
    vs. rental groups vs. sale groups)?
  - What's the cooldown between sends to avoid webot rate-limiting?

For now, `dispatch_slot()` is the unit-testable entry point. Once
Shmuel decides the trigger semantics, call it from `scheduler.py` (a
fire-and-forget task at slot time) or from a new admin endpoint
`/post-slots/{id}/auto-post`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import webot_client
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
    ones webot accepted. A partial failure (some groups OK, some failed)
    is NOT enough to flip the slot to POSTED — caller decides whether
    to mark it POSTED or leave it for retry.
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
    """Send `slot`'s property to every active matching WhatsApp group via webot.

    Returns a `DispatchResult` describing what happened. When the webot
    integration is not configured, returns immediately with
    `skipped_reason="webot_unconfigured"` so the caller can decide whether
    to fall back to the manual one-tap share flow.

    Idempotency: the caller controls whether to flip the slot's status.
    By default, ANY success marks the slot POSTED — partial failures are
    acceptable since webot occasionally drops sends and we don't want
    duplicate posts on retry. Set `mark_posted_on_success=False` to keep
    the slot in PENDING for caller-driven retry logic.
    """
    result = DispatchResult(slot_id=str(slot.id))

    if not settings.webot_api_token or not settings.webot_from_phone:
        result.skipped_reason = "webot_unconfigured"
        log.info("auto_poster: slot %s skipped — webot unconfigured", slot.id)
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
    media_link = _first_photo_url(photos)

    for group in groups:
        result.attempted += 1
        # webot identifies WhatsApp groups by their target identifier; this
        # is stored on the Group row's `target_url` (e.g. the group invite
        # code or webot-internal group ID Shmuel pastes in via admin).
        to = group.target_url or ""
        if not to:
            result.group_failures.append({"group": group.name, "error": "missing_target_url"})
            continue
        sent = await webot_client.send_message(
            to_phone_number=to,
            message=message,
            media_link=media_link,
        )
        if sent is None:
            result.group_failures.append({"group": group.name, "error": "webot_failure"})
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
