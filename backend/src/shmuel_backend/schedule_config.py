"""DB-backed posting schedule: load/create the single config row and turn it
into a SchedulePolicy the pure scheduler understands."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.models import ScheduleConfig
from shmuel_backend.scheduler import SchedulePolicy


async def get_or_create_schedule_config(session: AsyncSession) -> ScheduleConfig:
    """Return the singleton ScheduleConfig row, creating it (with env-default
    values) on first read."""
    cfg = await session.get(ScheduleConfig, "default")
    if cfg is None:
        cfg = ScheduleConfig(id="default")
        session.add(cfg)
        await session.flush()
    return cfg


def policy_from_config(cfg: ScheduleConfig) -> SchedulePolicy:
    return SchedulePolicy(
        tz=cfg.timezone,
        morning_slot=cfg.morning_slot,
        evening_slot=cfg.evening_slot,
        posts_per_slot=cfg.posts_per_slot,
        friday_block_after=cfg.friday_block_after,
        saturday_resume_at=cfg.saturday_resume_at,
    )
