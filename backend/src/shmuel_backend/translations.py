"""Content translation sync + public lookup API.

`sync_translations()` fetches properties, blog posts, and neighborhoods
from the WordPress REST API, extracts the translatable fields, and
translates each into ES / FR / HE via OpenAI. Translations are stored
in the `content_translations` table keyed by (content_type, content_slug,
lang, field). A `source_hash` (sha256 of the source English value) lets
the next sync skip unchanged fields and only re-translate edits.

The public `/public/translations` endpoint is what the Next.js rebuild
calls per page to merge translated fields into its WP-sourced data.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.config import settings
from shmuel_backend.db import SessionLocal, get_session
from shmuel_backend.models import ContentTranslation
from shmuel_backend.translation_client import translate

log = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

TARGET_LANGS: tuple[str, ...] = ("es", "fr", "he")
CONTENT_TYPES: tuple[str, ...] = ("property", "blog", "neighborhood")


# ---------------------------------------------------------------------
# Source extraction — turn WP REST payloads into {field_name: text} dicts
# ---------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Minimal HTML strip — translation works fine on the raw <p>/<ol> output,
    but we strip when computing the hash so cosmetic markup changes don't
    invalidate translations. The translated value preserves the source markup."""
    import re

    return re.sub(r"<[^>]+>", " ", html).strip()


def _hash_source(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _extract_property_fields(p: dict[str, Any]) -> dict[str, str]:
    """Return field_name → source_english_text for a property WP row.

    Skipped fields: street_name, neighborhood, price_shekels, beds, baths, sqm
    — those are proper nouns / numbers / measurements and should not translate.
    """
    out: dict[str, str] = {}
    acf = p.get("acf") or {}
    details = acf.get("details_properties") or {}
    title_html = (p.get("title") or {}).get("rendered") or ""
    if title_html:
        out["title"] = _strip_html(title_html)
    name = details.get("property_name")
    if name:
        out["property_name"] = name
    desc = acf.get("description") or {}
    if desc.get("paragraph_1"):
        out["description_p1"] = desc["paragraph_1"]
    if desc.get("paragraph_2"):
        out["description_p2"] = desc["paragraph_2"]
    more = acf.get("more_information") or []
    for i, item in enumerate(more):
        if isinstance(item, str) and item.strip():
            out[f"more_info_{i}"] = item
    return out


def _extract_blog_fields(p: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    title = (p.get("title") or {}).get("rendered") or ""
    if title:
        out["title"] = _strip_html(title)
    excerpt = (p.get("excerpt") or {}).get("rendered") or ""
    if excerpt:
        out["excerpt"] = excerpt
    content = (p.get("content") or {}).get("rendered") or ""
    if content:
        out["content"] = content
    return out


def _extract_neighborhood_fields(p: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    title = (p.get("title") or {}).get("rendered") or ""
    if title:
        # Neighborhood names are proper nouns — keep as-is even in other languages.
        # Don't translate the title field.
        pass
    content = (p.get("content") or {}).get("rendered") or ""
    if content:
        out["content"] = content
    return out


EXTRACTORS = {
    "property": _extract_property_fields,
    "blog": _extract_blog_fields,
    "neighborhood": _extract_neighborhood_fields,
}

WP_ENDPOINTS = {
    "property": "/properties",
    "blog": "/blog",
    "neighborhood": "/neighborhood",
}


# ---------------------------------------------------------------------
# Sync orchestration
# ---------------------------------------------------------------------

class SyncStats(BaseModel):
    content_type: str
    fetched: int = 0
    translated: int = 0
    refreshed: int = 0
    skipped: int = 0
    errors: int = 0


class SyncResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    per_type: list[SyncStats]
    total_translated: int


async def _fetch_wp(content_type: str) -> list[dict[str, Any]]:
    """Fetch every item of one type from WP REST."""
    out: list[dict[str, Any]] = []
    base = settings.wp_rest_base.rstrip("/") + WP_ENDPOINTS[content_type]
    page = 1
    async with httpx.AsyncClient(timeout=30.0) as http:
        while True:
            resp = await http.get(base, params={"per_page": 100, "page": page})
            if resp.status_code == 400 and page > 1:
                # WP REST returns 400 when paging past the last page.
                break
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return out


class _passthrough:
    """Async-context wrapper around an already-open session — lets sync code
    use a single `async with` whether we created the session here or got one
    from a test fixture. The wrapped session is never closed."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


async def _existing_hashes(
    session: AsyncSession,
    content_type: str,
) -> dict[tuple[str, str, str], str]:
    """Return {(slug, lang, field): source_hash} for everything we already have."""
    rows = (
        await session.execute(
            select(
                ContentTranslation.content_slug,
                ContentTranslation.lang,
                ContentTranslation.field,
                ContentTranslation.source_hash,
            ).where(ContentTranslation.content_type == content_type)
        )
    ).all()
    return {(r.content_slug, r.lang, r.field): r.source_hash for r in rows}


async def _upsert(
    session: AsyncSession,
    *,
    content_type: str,
    content_slug: str,
    lang: str,
    field: str,
    value: str,
    source_hash: str,
) -> None:
    """Dialect-agnostic upsert via SELECT-then-INSERT-or-UPDATE.

    The unique constraint on (content_type, content_slug, lang, field) means
    only one row can match. Two extra round-trips per write vs a Postgres-native
    ON CONFLICT, but trivial at this volume (~thousands of fields total) and
    keeps tests on SQLite in-memory."""
    existing = (
        await session.execute(
            select(ContentTranslation).where(
                ContentTranslation.content_type == content_type,
                ContentTranslation.content_slug == content_slug,
                ContentTranslation.lang == lang,
                ContentTranslation.field == field,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ContentTranslation(
                content_type=content_type,
                content_slug=content_slug,
                lang=lang,
                field=field,
                value=value,
                source_hash=source_hash,
            )
        )
    else:
        existing.value = value
        existing.source_hash = source_hash
    # Flush each row immediately so the session never accumulates pending
    # writes that would be autoflushed on the NEXT _upsert's SELECT — that
    # cascade is what hits Supabase's statement timeout under a long sync.
    await session.flush()


async def sync_translations(
    session: AsyncSession | None = None,
    *,
    content_types: tuple[str, ...] = CONTENT_TYPES,
    target_langs: tuple[str, ...] = TARGET_LANGS,
) -> SyncResult:
    """Run a full sync: fetch WP content, translate new/changed fields.

    Opens a fresh DB session per item (vs. holding one across the whole run)
    so the connection isn't tied up across slow OpenAI awaits — Supabase's
    transaction pooler cycles long-idle sessions and would otherwise blow
    the statement timeout. The `session` parameter is ignored at runtime and
    exists only for tests that want to override SessionLocal via dependency
    overrides; production paths always use a fresh session per item.

    Idempotent — re-running with no source changes is a no-op (matched hashes
    are skipped). Translation failures for individual fields are logged and
    counted; one bad field doesn't block the rest of the run.
    """
    # Tests pass an in-memory session; reuse it for the whole run so the
    # rollback at fixture teardown sees everything. Prod uses fresh sessions.
    test_session = session
    started = datetime.now(UTC)
    per_type: list[SyncStats] = []
    for ct in content_types:
        stats = SyncStats(content_type=ct)
        try:
            items = await _fetch_wp(ct)
        except httpx.HTTPError as exc:
            log.warning("WP fetch failed for %s: %s", ct, exc)
            stats.errors += 1
            per_type.append(stats)
            continue
        stats.fetched = len(items)

        # Load the existing-hashes map once, with a short-lived session.
        if test_session is not None:
            existing = await _existing_hashes(test_session, ct)
        else:
            async with SessionLocal() as s:
                existing = await _existing_hashes(s, ct)

        extractor = EXTRACTORS[ct]
        log.info("  %s: %d items to process", ct, len(items))
        for idx, item in enumerate(items, start=1):
            slug = item.get("slug")
            if not slug:
                continue
            fields = extractor(item)
            tasks: list[tuple[str, str, str, str, bool]] = []
            for field, source_text in fields.items():
                source_hash = _hash_source(_strip_html(source_text))
                for lang in target_langs:
                    if existing.get((slug, lang, field)) == source_hash:
                        stats.skipped += 1
                        continue
                    is_refresh = (slug, lang, field) in existing
                    tasks.append((field, source_text, source_hash, lang, is_refresh))
            if not tasks:
                continue

            # OpenAI calls run WITHOUT any DB session held — the connection
            # was returned to the pool when _existing_hashes finished.
            results = await asyncio.gather(
                *(translate(text=t[1], target_lang=t[3]) for t in tasks),
                return_exceptions=True,
            )

            # Open a fresh session JUST for the upserts (sub-second total).
            write_session_ctx = (
                _passthrough(test_session) if test_session is not None else SessionLocal()
            )
            async with write_session_ctx as s:
                for (field, _source_text, source_hash, lang, is_refresh), result in zip(
                    tasks, results, strict=True,
                ):
                    if isinstance(result, BaseException):
                        log.warning(
                            "translate raised for %s/%s/%s/%s: %s",
                            ct, slug, lang, field, result,
                        )
                        stats.errors += 1
                        continue
                    if result is None:
                        stats.errors += 1
                        continue
                    await _upsert(
                        s,
                        content_type=ct,
                        content_slug=slug,
                        lang=lang,
                        field=field,
                        value=result,
                        source_hash=source_hash,
                    )
                    if is_refresh:
                        stats.refreshed += 1
                    else:
                        stats.translated += 1
                await s.commit()

            for field, _src, source_hash, lang, _ in tasks:
                existing[(slug, lang, field)] = source_hash
            log.info("    [%d/%d] %s: %d translations written", idx, len(items), slug, len(tasks))
        per_type.append(stats)
        log.info(
            "Translation sync %s: fetched=%d translated=%d refreshed=%d skipped=%d errors=%d",
            ct, stats.fetched, stats.translated, stats.refreshed, stats.skipped, stats.errors,
        )
    finished = datetime.now(UTC)
    return SyncResult(
        started_at=started,
        finished_at=finished,
        duration_seconds=(finished - started).total_seconds(),
        per_type=per_type,
        total_translated=sum(s.translated + s.refreshed for s in per_type),
    )


# ---------------------------------------------------------------------
# Public API — what the rebuild calls per page
# ---------------------------------------------------------------------

public_router = APIRouter(prefix="/public/translations", tags=["translations"])


class TranslationBundle(BaseModel):
    content_type: str
    content_slug: str
    lang: str
    fields: dict[str, str]


@public_router.get("", response_model=list[TranslationBundle])
async def get_translations(
    session: SessionDep,
    content_type: str = Query(..., pattern="^(property|blog|neighborhood)$"),
    slugs: str = Query(..., description="Comma-separated content slugs"),
    lang: str = Query(..., pattern="^(es|fr|he)$"),
) -> list[TranslationBundle]:
    """Return field translations for one or more items, in the target language.

    Missing translations are simply absent from the response — callers fall back
    to the English source field. Empty `slugs` returns an empty list.
    """
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return []
    rows = (
        await session.execute(
            select(ContentTranslation).where(
                ContentTranslation.content_type == content_type,
                ContentTranslation.lang == lang,
                ContentTranslation.content_slug.in_(slug_list),
            )
        )
    ).scalars().all()
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        grouped[row.content_slug][row.field] = row.value
    return [
        TranslationBundle(
            content_type=content_type,
            content_slug=slug,
            lang=lang,
            fields=grouped.get(slug, {}),
        )
        for slug in slug_list
    ]


# ---------------------------------------------------------------------
# Admin API — manual sync trigger (api-key gated by middleware)
# ---------------------------------------------------------------------

admin_router = APIRouter(prefix="/translations", tags=["translations"])


@admin_router.post("/sync", response_model=SyncResult)
async def trigger_sync() -> SyncResult:
    """Run a full translation sync now. Safe to call repeatedly — unchanged
    fields are skipped via source-hash comparison.

    No session dep — sync_translations() opens its own fresh sessions per item
    so a long sync doesn't tie one connection up across slow OpenAI awaits.
    """
    return await sync_translations()
