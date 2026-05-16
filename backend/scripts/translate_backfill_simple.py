"""Minimal asyncpg-only backfill. Bypasses SQLAlchemy entirely.

Why a separate script: the SQLAlchemy + asyncpg path against Supabase keeps
hitting statement_timeout / pooler quirks. This version uses one autocommit
asyncpg connection, runs every INSERT/SELECT against it directly, and
processes one property's worth of translations at a time. Same logic as
sync_translations() but with the abstractions stripped.

Usage:
    cd backend
    DATABASE_URL=<direct supabase url> \
    OPENAI_API_KEY=sk-... \
    .venv/bin/python scripts/translate_backfill_simple.py
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sys
import uuid

import asyncpg
import httpx

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
log = logging.getLogger("backfill")

WP_BASE = os.environ.get("WP_REST_BASE", "https://realestateadmin2025.classicjerusalem.com/wp-json/wp/v2")
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
MODEL = os.environ.get("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini")
TARGET_LANGS = ("es", "fr", "he")
# Per-content-type cap on items processed. 0 = unlimited. Useful for smoke-testing
# the INSERT path on Supabase without burning hundreds of OpenAI calls.
LIMIT = int(os.environ.get("BACKFILL_LIMIT", "0"))

LANG_NAMES = {"es": "Spanish", "fr": "French", "he": "Hebrew"}

SYSTEM_PROMPT = (
    "You are a professional translator for a Jerusalem real-estate brokerage. "
    "Translate the user's text from English to {target_lang}. "
    "Preserve real-estate terminology, neighborhood names, street names, and prices verbatim. "
    "Output only the translation — no quotes, no commentary, no preamble. "
    "Match the source's tone and formatting (paragraph breaks, lists)."
)


def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def hash_source(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


WP_FIELDS = {
    # Slim each list response so WP doesn't return 13MB JSON. Mirrors the
    # frontend's _fields= usage. Whatever isn't here gets dropped server-side.
    "property": "slug,title,acf.details_properties,acf.description,acf.more_information",
    "blog": "slug,title,excerpt,content",
    "neighborhood": "slug,content",
}


_WP_ENDPOINTS = {
    "property": "/properties",
    "blog": "/blog",
    "neighborhood": "/neighborhood",
}


async def fetch_wp(http: httpx.AsyncClient, content_type: str) -> list[dict]:
    """Page through WP REST and return every item."""
    endpoint = _WP_ENDPOINTS[content_type]
    out: list[dict] = []
    page = 1
    while True:
        r = await http.get(
            f"{WP_BASE}{endpoint}",
            params={"per_page": 50, "page": page, "_fields": WP_FIELDS[content_type]},
            timeout=90.0,
        )
        if r.status_code == 400 and page > 1:
            break
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 50:
            break
        page += 1
    return out


def extract_property(p: dict) -> dict[str, str]:
    acf = p.get("acf") or {}
    details = acf.get("details_properties") or {}
    out: dict[str, str] = {}
    title = (p.get("title") or {}).get("rendered") or ""
    if title:
        out["title"] = strip_html(title)
    if details.get("property_name"):
        out["property_name"] = details["property_name"]
    desc = acf.get("description") or {}
    if desc.get("paragraph_1"):
        out["description_p1"] = desc["paragraph_1"]
    if desc.get("paragraph_2"):
        out["description_p2"] = desc["paragraph_2"]
    for i, item in enumerate(acf.get("more_information") or []):
        if isinstance(item, str) and item.strip():
            out[f"more_info_{i}"] = item
    return out


def extract_blog(p: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    title = (p.get("title") or {}).get("rendered") or ""
    if title:
        out["title"] = strip_html(title)
    excerpt = (p.get("excerpt") or {}).get("rendered") or ""
    if excerpt:
        out["excerpt"] = excerpt
    content = (p.get("content") or {}).get("rendered") or ""
    if content:
        out["content"] = content
    return out


def extract_neighborhood(p: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    content = (p.get("content") or {}).get("rendered") or ""
    if content:
        out["content"] = content
    return out


EXTRACTORS = {
    "property": extract_property,
    "blog": extract_blog,
    "neighborhood": extract_neighborhood,
}


async def translate(http: httpx.AsyncClient, text: str, target_lang: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return ""
    if target_lang not in LANG_NAMES:
        return None
    try:
        r = await http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.format(
                            target_lang=LANG_NAMES[target_lang],
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0.2,
            },
            timeout=30.0,
        )
        if r.status_code >= 400:
            log.warning("OpenAI %s: %s", r.status_code, r.text[:300])
            return None
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "").strip()
        return content or None
    except httpx.HTTPError as exc:
        log.warning("OpenAI request failed: %s", exc)
        return None


UPSERT_SQL = """
INSERT INTO content_translations (id, content_type, content_slug, lang, field, value, source_hash)
VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
ON CONFLICT (content_type, content_slug, lang, field)
DO UPDATE SET value = EXCLUDED.value, source_hash = EXCLUDED.source_hash, updated_at = now()
"""


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        DB_URL,
        statement_cache_size=0,
        server_settings={"statement_timeout": "300000"},
    )


async def main() -> None:
    log.info("backfill starting — model=%s langs=%s", MODEL, ",".join(TARGET_LANGS))

    async with httpx.AsyncClient() as http:
        for ct in ("property", "blog", "neighborhood"):
            log.info("=== %s ===", ct)
            items = await fetch_wp(http, ct)
            if LIMIT:
                items = items[:LIMIT]
                log.info("  fetched %d items (capped at BACKFILL_LIMIT=%d)", len(items), LIMIT)
            else:
                log.info("  fetched %d items", len(items))

            # Load existing hashes for this content_type with a short-lived connection.
            conn = await _connect()
            try:
                existing_rows = await conn.fetch(
                    "SELECT content_slug, lang, field, source_hash"
                    " FROM content_translations WHERE content_type=$1",
                    ct,
                )
            finally:
                await conn.close()
            existing = {
                (r["content_slug"], r["lang"], r["field"]): r["source_hash"]
                for r in existing_rows
            }
            log.info("  existing rows for %s: %d", ct, len(existing))

            extractor = EXTRACTORS[ct]
            stats = {"new": 0, "refreshed": 0, "skipped": 0, "errors": 0}

            for idx, item in enumerate(items, start=1):
                slug = item.get("slug")
                if not slug:
                    continue
                fields = extractor(item)
                tasks: list[tuple[str, str, str, str, bool]] = []
                for field, source_text in fields.items():
                    sh = hash_source(strip_html(source_text))
                    for lang in TARGET_LANGS:
                        if existing.get((slug, lang, field)) == sh:
                            stats["skipped"] += 1
                            continue
                        is_refresh = (slug, lang, field) in existing
                        tasks.append((field, source_text, sh, lang, is_refresh))
                if not tasks:
                    log.info("  [%d/%d] %s: nothing new", idx, len(items), slug)
                    continue

                # OpenAI calls — no DB connection open.
                results = await asyncio.gather(
                    *(translate(http, t[1], t[3]) for t in tasks),
                    return_exceptions=True,
                )

                # Now open a fresh connection JUST for the upserts and close it.
                conn = await _connect()
                try:
                    writes = 0
                    paired = zip(tasks, results, strict=True)
                    for (field, _src, sh, lang, is_refresh), res in paired:
                        if isinstance(res, BaseException) or res is None:
                            stats["errors"] += 1
                            continue
                        await conn.execute(UPSERT_SQL, uuid.uuid4(), ct, slug, lang, field, res, sh)
                        existing[(slug, lang, field)] = sh
                        writes += 1
                        if is_refresh:
                            stats["refreshed"] += 1
                        else:
                            stats["new"] += 1
                finally:
                    await conn.close()

                log.info("  [%d/%d] %s: wrote %d", idx, len(items), slug, writes)

            log.info("  %s done: new=%d refreshed=%d skipped=%d errors=%d",
                     ct, stats["new"], stats["refreshed"], stats["skipped"], stats["errors"])

    log.info("backfill complete")


if __name__ == "__main__":
    asyncio.run(main())
