"""Glue between stored photos (Drive) and the pure collage builder.

Downloads up to N of a property's photos and renders the share collage. Returns
None (never raises for the "no material" cases) so callers can fall back to a
text-only post or a friendly 404.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.cloud.crypto import decrypt
from shmuel_backend.cloud.drive import GoogleDriveStorage
from shmuel_backend.cloud.storage import CloudStorageError
from shmuel_backend.collage import CollageError, build_collage
from shmuel_backend.models import CloudConnection, CloudPhoto

PROVIDER_GOOGLE = "google_drive"
MAX_COLLAGE_PHOTOS = 4

# Stateless — safe to share across requests.
_storage = GoogleDriveStorage()


async def render_property_collage(
    session: AsyncSession, property_id: uuid.UUID
) -> bytes | None:
    """PNG bytes for the property's collage, or None if it can't be built
    (no Drive connection, no photos, or none of them download)."""
    conn = (
        await session.execute(
            select(CloudConnection).where(
                CloudConnection.provider == PROVIDER_GOOGLE
            )
        )
    ).scalar_one_or_none()
    if conn is None:
        return None

    photos = list(
        (
            await session.execute(
                select(CloudPhoto)
                .where(CloudPhoto.property_id == property_id)
                .order_by(CloudPhoto.created_at)
                .limit(MAX_COLLAGE_PHOTOS)
            )
        ).scalars()
    )
    if not photos:
        return None

    token = decrypt(conn.encrypted_refresh_token)
    blobs: list[bytes] = []
    for photo in photos:
        try:
            blobs.append(await _storage.download_file(token, photo.external_id))
        except CloudStorageError:
            continue  # skip a single bad file rather than fail the collage
    if not blobs:
        return None

    try:
        return build_collage(blobs)
    except CollageError:
        return None
