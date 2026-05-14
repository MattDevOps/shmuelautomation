"""One-time backfill: translate every property, blog post, and neighborhood
in WP into ES, FR, HE, and store the results in content_translations.

Re-running is idempotent — unchanged fields are skipped via the source-hash
check inside sync_translations(). Safe to run from anywhere with the same
DATABASE_URL + OPENAI_API_KEY env vars as the deployed backend.

Usage:
    cd backend
    uv run python scripts/translate_backfill.py
    # or: .venv/bin/python scripts/translate_backfill.py
"""
from __future__ import annotations

import asyncio
import logging

from shmuel_backend.db import SessionLocal
from shmuel_backend.logging_config import configure_logging
from shmuel_backend.translations import sync_translations


async def main() -> None:
    configure_logging("development")
    log = logging.getLogger(__name__)
    log.info("Starting translation backfill")
    async with SessionLocal() as session:
        result = await sync_translations(session)
    log.info(
        "Backfill complete in %.1fs — translated %d (new+refreshed)",
        result.duration_seconds,
        result.total_translated,
    )
    for s in result.per_type:
        log.info(
            "  %s: fetched=%d new=%d refreshed=%d skipped=%d errors=%d",
            s.content_type, s.fetched, s.translated, s.refreshed, s.skipped, s.errors,
        )


if __name__ == "__main__":
    asyncio.run(main())
