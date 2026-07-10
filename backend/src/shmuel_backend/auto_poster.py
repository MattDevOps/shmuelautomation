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

import asyncio
import base64
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import whatsapp_client
from shmuel_backend.collage_service import render_share_pack
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

# How many groups get their send chains run at once, and the pause between
# consecutive image sends within one group (a burst of back-to-back images
# is both spam-shaped and ban-bait).
_GROUP_SEND_CONCURRENCY = 3
_INTER_IMAGE_DELAY_S = 1.0


@dataclass
class DispatchResult:
    """Outcome of attempting to send a slot to all matching groups.

    `attempted` counts groups we tried to reach; `succeeded` counts the
    ones the daemon accepted. A partial failure (some groups OK, some
    failed) is NOT enough to flip the slot to POSTED; the caller decides
    whether to mark it POSTED or leave it for retry. `group_failures`
    lists only groups that did NOT get the post; follow-up branded photos
    that fail are tallied in `photo_failures` instead (the group still got
    the collage + caption).
    """

    slot_id: str
    attempted: int = 0
    succeeded: int = 0
    skipped_reason: str | None = None
    group_failures: list[dict[str, str]] = field(default_factory=list)
    photo_failures: int = 0


@dataclass
class _GroupOutcome:
    """One group's send chain result, merged into DispatchResult by the caller."""

    succeeded: bool
    failure: dict[str, str] | None = None
    photo_failures: int = 0


async def _send_group_post(
    group: Group,
    *,
    slot_id: str,
    message: str,
    collage_b64: str | None,
    photo_b64s: list[str],
    sem: asyncio.Semaphore,
) -> _GroupOutcome:
    """Send one group its post: collage (or text), then each branded photo.

    Order within the group is guaranteed (collage first, then photos, with a
    pacing delay between images); `sem` bounds how many groups send at once.
    """
    # `target_url` on the Group row holds the WhatsApp group JID (e.g.
    # `12345-67890@g.us`) or bare id. Admin populates it from the
    # daemon's GET /groups list rather than free-form paste.
    to = group.target_url or ""
    if not to:
        return _GroupOutcome(
            succeeded=False,
            failure={"group": group.name, "error": "missing_target_url"},
        )

    async with sem:
        if collage_b64 is not None:
            sent = await whatsapp_client.send_image_to_group(
                group_id=to,
                image_base64=collage_b64,
                caption=message,
            )
        else:
            sent = await whatsapp_client.send_to_group(
                group_id=to,
                message=message,
            )
        if sent is None:
            return _GroupOutcome(
                succeeded=False,
                failure={"group": group.name, "error": "daemon_failure"},
            )

        # Follow the collage with each branded photo (no caption). The group
        # already counts as succeeded (the collage + caption landed), so a
        # dropped photo is logged and tallied but doesn't flip the group.
        outcome = _GroupOutcome(succeeded=True)
        for photo_b64 in photo_b64s:
            await asyncio.sleep(_INTER_IMAGE_DELAY_S)
            photo_sent = await whatsapp_client.send_image_to_group(
                group_id=to,
                image_base64=photo_b64,
                caption="",
            )
            if photo_sent is None:
                log.warning(
                    "auto_poster: slot %s: branded photo send failed for group %s",
                    slot_id, group.name,
                )
                outcome.photo_failures += 1
        return outcome


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

    # Fetch photos once for the message body.
    photos_rows = await session.execute(
        select(CloudPhoto).where(CloudPhoto.property_id == prop.id).order_by(CloudPhoto.created_at)
    )
    photos = list(photos_rows.scalars().all())
    message = _build_message(prop, photos)

    # Build the share pack (collage + individually branded photos) once and
    # reuse the encoded payloads for every group send. When there are no
    # photos / no Drive connection the pack is None and we fall back to a
    # text-only post.
    collage_b64: str | None = None
    photo_b64s: list[str] = []
    pack = await render_share_pack(session, prop.id)
    if pack is not None:
        collage_b64 = base64.b64encode(pack.collage_png).decode("ascii")
        photo_b64s = [base64.b64encode(jpeg).decode("ascii") for jpeg in pack.photos]

    # Groups run concurrently (bounded) while each group's own sends stay
    # sequential and paced, so the whole dispatch doesn't take minutes but
    # also doesn't hit one group with a machine-gun burst of images.
    sem = asyncio.Semaphore(_GROUP_SEND_CONCURRENCY)
    outcomes = await asyncio.gather(
        *(
            _send_group_post(
                group,
                slot_id=str(slot.id),
                message=message,
                collage_b64=collage_b64,
                photo_b64s=photo_b64s,
                sem=sem,
            )
            for group in groups
        )
    )
    for outcome in outcomes:
        result.attempted += 1
        if outcome.succeeded:
            result.succeeded += 1
        if outcome.failure is not None:
            result.group_failures.append(outcome.failure)
        result.photo_failures += outcome.photo_failures

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
