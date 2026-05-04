from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from shmuel_backend.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict[str, Any]:
    # Supabase's transaction pooler (pgbouncer in transaction mode) doesn't
    # support server-side prepared statements; another session may have
    # already prepared a statement under the auto-generated name we reuse.
    # Disable asyncpg's prepared-statement cache so we never name them.
    if "asyncpg" in settings.database_url:
        return {"connect_args": {"statement_cache_size": 0}}
    return {}


engine = create_async_engine(settings.database_url, future=True, **_engine_kwargs())
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
