"""One-time backfill: translate every property, blog post, and neighborhood
in WP into ES, FR, HE, and store the results in content_translations.

Re-running is idempotent — unchanged fields are skipped via the source-hash
check inside sync_translations(). Safe to run from anywhere with the same
DATABASE_URL + OPENAI_API_KEY env vars as the deployed backend.

Calls the same sync_translations() the HTTP /translations/sync endpoint uses,
so success here proves the production path works against Supabase.

Usage:
    cd backend
    uv run python scripts/translate_backfill.py
    # or: .venv/bin/python scripts/translate_backfill.py
"""
from __future__ import annotations

import asyncio
import logging

from shmuel_backend.db import engine
from shmuel_backend.logging_config import configure_logging
from shmuel_backend.translations import sync_translations


async def main() -> None:
    configure_logging("development")
    log = logging.getLogger(__name__)
    log.info("Starting translation backfill")
    try:
        # Pass session=None so sync_translations opens a fresh session per
        # item via SessionLocal — that's the pattern that survives Supabase's
        # tight per-statement timeout across long OpenAI awaits.
        result = await sync_translations(None)
    finally:
        await engine.dispose()
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
