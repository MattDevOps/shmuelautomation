"""Glue between stored photos (Drive) and the pure branding builders.

Downloads a property's photo candidates once (in parallel, one token refresh),
drops near-duplicate shots (dHash), and renders the share pack: the collage of
the 4 most diverse photos plus each distinct photo individually branded. All
Pillow work runs off the event loop, and rendered packs sit in a small TTL
cache so the collage endpoint, the zip download, and the auto-poster reuse one
render. Returns None (never raises for the "no material" cases) so callers can
fall back to a text-only post or a friendly 404.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.cloud.connections import get_google_connection
from shmuel_backend.cloud.crypto import decrypt
from shmuel_backend.cloud.drive import GoogleDriveStorage, refresh_access_token
from shmuel_backend.cloud.storage import CloudStorageError
from shmuel_backend.collage import (
    CollageError,
    build_collage_from_images,
    load_image,
    watermark_image,
    watermark_photo,
)
from shmuel_backend.models import CloudConnection, CloudPhoto
from shmuel_backend.photo_select import select_diverse

log = logging.getLogger(__name__)

MAX_COLLAGE_PHOTOS = 4
# Fetch more than the collage needs so dedup still leaves 4 distinct shots
# even when the gallery is half re-exports of the same room.
MAX_CANDIDATE_PHOTOS = 12
MAX_PACK_PHOTOS = 8
_DOWNLOAD_CONCURRENCY = 4

# Rendered packs are cached briefly so the admin preview, the zip download,
# and a dispatch don't each redo 12 Drive downloads plus the Pillow work.
# The key includes every candidate photo's (id, checksum); photos are
# immutable per checksum, so add/delete/replace changes the key and stale
# entries simply age out.
_PACK_CACHE_TTL_S = 600.0
_PACK_CACHE_MAX = 16
_CacheKey = tuple[uuid.UUID, frozenset[tuple[uuid.UUID, str]]]
_pack_cache: dict[_CacheKey, tuple[float, SharePack]] = {}

# Stateless: safe to share across requests.
_storage = GoogleDriveStorage()


@dataclass
class SharePack:
    """Everything a post needs: the collage plus each branded photo."""

    collage_png: bytes
    photos: list[bytes]  # branded JPEGs, diversity order


def _cache_get(key: _CacheKey) -> SharePack | None:
    entry = _pack_cache.get(key)
    if entry is None:
        return None
    stamp, pack = entry
    if time.monotonic() - stamp > _PACK_CACHE_TTL_S:
        del _pack_cache[key]
        return None
    return pack


def _cache_put(key: _CacheKey, pack: SharePack) -> None:
    if len(_pack_cache) >= _PACK_CACHE_MAX:
        oldest = min(_pack_cache, key=lambda k: _pack_cache[k][0])
        del _pack_cache[oldest]
    _pack_cache[key] = (time.monotonic(), pack)


async def _candidate_photos(
    session: AsyncSession, property_id: uuid.UUID
) -> list[CloudPhoto]:
    return list(
        (
            await session.execute(
                select(CloudPhoto)
                .where(CloudPhoto.property_id == property_id)
                .order_by(CloudPhoto.created_at)
                .limit(MAX_CANDIDATE_PHOTOS)
            )
        ).scalars()
    )


async def _download_blobs(
    conn: CloudConnection, external_ids: list[str]
) -> list[bytes]:
    """Fetch the candidate files in parallel with ONE access-token refresh.

    Skips (rather than fails on) individual bad files; gallery order is kept.
    """
    try:
        access = await refresh_access_token(decrypt(conn.encrypted_refresh_token))
    except CloudStorageError:
        log.warning("share_pack: drive token refresh failed; no pack")
        return []

    sem = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)

    async def fetch(external_id: str) -> bytes | None:
        async with sem:
            try:
                return await _storage.download_file_with_access(access, external_id)
            except CloudStorageError:
                return None  # skip a single bad file rather than fail the pack

    results = await asyncio.gather(*(fetch(e) for e in external_ids))
    return [blob for blob in results if blob is not None]


def _render_pack_sync(
    blobs: list[bytes], *, max_photos: int, property_id: uuid.UUID
) -> SharePack | None:
    """The whole CPU stage: decode once, dHash dedup, collage, watermarks.

    Synchronous on purpose; callers run it via asyncio.to_thread so Pillow
    never blocks the event loop.
    """
    images = [img for blob in blobs if (img := load_image(blob)) is not None]
    if not images:
        return None

    keep = select_diverse(images, k=len(images))
    if len(keep) < len(images):
        log.info(
            "share_pack: property %s: dedup dropped %d of %d candidate photo(s)",
            property_id, len(images) - len(keep), len(images),
        )

    # Dedup must never shrink the collage below what the gallery supports:
    # backfill skipped candidates (gallery order) up to 4 tiles. The branded
    # photo set stays deduped; only the collage gets backfilled.
    collage_idx = list(keep[:MAX_COLLAGE_PHOTOS])
    want = min(MAX_COLLAGE_PHOTOS, len(images))
    for i in range(len(images)):
        if len(collage_idx) >= want:
            break
        if i not in collage_idx:
            collage_idx.append(i)

    try:
        collage_png = build_collage_from_images([images[i] for i in collage_idx])
    except CollageError:
        return None

    branded: list[bytes] = []
    for i in keep[:max_photos]:
        try:
            branded.append(watermark_image(images[i]))
        except Exception:
            # One bad photo must never sink the pack (or a dispatch).
            log.exception(
                "share_pack: property %s: watermark failed for photo #%d",
                property_id, i,
            )
    return SharePack(collage_png=collage_png, photos=branded)


async def render_share_pack(
    session: AsyncSession,
    property_id: uuid.UUID,
    *,
    max_photos: int = MAX_PACK_PHOTOS,
    include_branded: bool = True,
) -> SharePack | None:
    """The property's share pack, or None if there's nothing to build it from.

    Collage from the 4 most diverse photos; individual branded photos are the
    deduped set in diversity order, capped at `max_photos`. Pass
    `include_branded=False` when only the collage matters; the full pack is
    still rendered and cached once, but the returned photos list is empty.
    """
    conn = await get_google_connection(session)
    if conn is None:
        return None
    photos = await _candidate_photos(session, property_id)
    if not photos:
        return None

    key: _CacheKey = (property_id, frozenset((p.id, p.checksum) for p in photos))
    pack = _cache_get(key)
    if pack is None:
        blobs = await _download_blobs(conn, [p.external_id for p in photos])
        if not blobs:
            return None
        pack = await asyncio.to_thread(
            _render_pack_sync, blobs,
            max_photos=MAX_PACK_PHOTOS, property_id=property_id,
        )
        if pack is None:
            return None
        _cache_put(key, pack)

    branded = list(pack.photos[:max_photos]) if include_branded else []
    return SharePack(collage_png=pack.collage_png, photos=branded)


async def render_property_collage(
    session: AsyncSession, property_id: uuid.UUID
) -> bytes | None:
    """PNG bytes for the property's collage, or None if it can't be built
    (no Drive connection, no photos, or none of them download)."""
    pack = await render_share_pack(session, property_id, include_branded=False)
    return pack.collage_png if pack is not None else None


async def render_branded_photo(
    session: AsyncSession, property_id: uuid.UUID, photo_id: uuid.UUID
) -> bytes | None:
    """Branded JPEG for one of the property's photos, or None when the photo
    doesn't exist / doesn't belong to the property / can't be fetched."""
    conn = await get_google_connection(session)
    if conn is None:
        return None

    photo = (
        await session.execute(
            select(CloudPhoto).where(
                CloudPhoto.id == photo_id,
                CloudPhoto.property_id == property_id,
            )
        )
    ).scalar_one_or_none()
    if photo is None:
        return None

    try:
        blob = await _storage.download_file(
            decrypt(conn.encrypted_refresh_token), photo.external_id
        )
    except CloudStorageError:
        return None
    try:
        return await asyncio.to_thread(watermark_photo, blob)
    except Exception:
        # Unusable bytes (or any Pillow surprise) reads as "no photo", not 500.
        log.exception(
            "share_pack: property %s: branded render failed for photo %s",
            property_id, photo_id,
        )
        return None
