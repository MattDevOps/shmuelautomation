"""Shared lookup for the single per-provider CloudConnection row."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.models import CloudConnection

PROVIDER_GOOGLE = "google_drive"


async def get_google_connection(session: AsyncSession) -> CloudConnection | None:
    """The Google Drive connection row, or None when Drive isn't connected."""
    result = await session.execute(
        select(CloudConnection).where(CloudConnection.provider == PROVIDER_GOOGLE)
    )
    return result.scalar_one_or_none()
