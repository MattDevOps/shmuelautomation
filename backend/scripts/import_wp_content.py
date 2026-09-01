"""Mirror WordPress site content (blog, neighbourhoods, pages) into our backend.

This is the content half of retiring WordPress. It copies the three content
types the public site still reads from WP into `blog_posts`, `neighborhoods`
and `site_pages`.

Nothing public reads those tables yet — the frontend keeps rendering from
WordPress until the per-type toggles are switched on. So this is safe to run
against production at any time: it only ever fills tables nobody is serving.

Idempotent. Rows are matched on `wp_id`, so a re-run updates what it created
last time instead of duplicating. Run it as often as you like to keep the
mirror fresh while WordPress carries on being the live source.

Usage (from backend/):
    uv run python scripts/import_wp_content.py --dry-run   # read WP, write nothing
    uv run python scripts/import_wp_content.py             # import everything
    uv run python scripts/import_wp_content.py --only blog # one type

Point it at production by exporting the deployed DATABASE_URL.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select

from shmuel_backend.db import SessionLocal, engine
from shmuel_backend.models import BlogPost, Neighborhood, SitePage

WP_BASE = "https://realestateadmin2025.classicjerusalem.com/wp-json/wp/v2"
PER_PAGE = 100
TIMEOUT = 60.0

# Pages worth mirroring. The WP install also carries drafts, samples and
# route-placeholder pages ("properties", "listings", "blogposts") that exist
# only to reserve a URL and hold no content the site reads.
PAGE_SLUGS = (
    "home",
    "contact-info-classic-jerusalem",
    "contact",
    "sell-your-aparment",
    "airbnb-your-aparment",
    "rent-your-apartment-long-term",
    "value-your-property",
    "join-our-team",
    "neighborhoods",
)


@dataclass
class Result:
    created: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)

    def line(self, label: str) -> str:
        s = f"  {label:16s} created {self.created:3d}  updated {self.updated:3d}"
        if self.skipped:
            s += f"  skipped {len(self.skipped)}"
        return s


def _rendered(node: Any) -> str:
    """WP wraps most text as {"rendered": "<p>..."}; tolerate plain strings."""
    if isinstance(node, dict):
        return str(node.get("rendered") or "")
    return str(node or "")


def _image_url(img: Any) -> str | None:
    """Pull a usable URL out of an ACF image field (object or bare string)."""
    if isinstance(img, str):
        return img or None
    if isinstance(img, dict):
        sizes = img.get("sizes") or {}
        for key in ("large", "medium_large", "full"):
            if sizes.get(key):
                return str(sizes[key])
        if img.get("url"):
            return str(img["url"])
    return None


def _parsed_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


async def _fetch_all(client: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
    """Page through a WP collection until it runs out."""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        r = await client.get(
            f"{WP_BASE}/{path}", params={"per_page": PER_PAGE, "page": page}
        )
        if r.status_code == 400 and page > 1:
            break  # WP returns 400 past the last page
        r.raise_for_status()
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
    return out


async def import_blog(session: Any, rows: list[dict[str, Any]], dry: bool) -> Result:
    res = Result()
    for row in rows:
        wp_id = int(row["id"])
        acf = row.get("acf") or {}
        existing = (
            await session.execute(select(BlogPost).where(BlogPost.wp_id == wp_id))
        ).scalar_one_or_none()
        values = {
            "slug": row["slug"],
            "title": _rendered(row.get("title")),
            "content_html": _rendered(row.get("content")),
            "excerpt_html": _rendered(row.get("excerpt")) or None,
            "image_url": _image_url(acf.get("imagepost")),
            "published_at": _parsed_date(row.get("date")),
        }
        if existing is None:
            if not dry:
                session.add(BlogPost(wp_id=wp_id, **values))
            res.created += 1
        else:
            if not dry:
                for k, v in values.items():
                    setattr(existing, k, v)
            res.updated += 1
    return res


async def import_neighborhoods(
    session: Any, rows: list[dict[str, Any]], dry: bool
) -> Result:
    res = Result()
    for order, row in enumerate(sorted(rows, key=lambda r: _rendered(r.get("title")))):
        wp_id = int(row["id"])
        acf = row.get("acf") or {}
        existing = (
            await session.execute(
                select(Neighborhood).where(Neighborhood.wp_id == wp_id)
            )
        ).scalar_one_or_none()
        values = {
            "slug": row["slug"],
            "title": _rendered(row.get("title")),
            "content_html": _rendered(row.get("content")),
            "card_image_url": _image_url(acf.get("image_card")),
            "hero_image_url": _image_url(acf.get("imagepost")),
            "sort_order": order,
        }
        if existing is None:
            if not dry:
                session.add(Neighborhood(wp_id=wp_id, **values))
            res.created += 1
        else:
            if not dry:
                for k, v in values.items():
                    setattr(existing, k, v)
            res.updated += 1
    return res


async def import_pages(session: Any, rows: list[dict[str, Any]], dry: bool) -> Result:
    res = Result()
    by_slug = {r["slug"]: r for r in rows}
    for slug in PAGE_SLUGS:
        row = by_slug.get(slug)
        if row is None:
            res.skipped.append(slug)
            continue
        wp_id = int(row["id"])
        existing = (
            await session.execute(select(SitePage).where(SitePage.wp_id == wp_id))
        ).scalar_one_or_none()
        acf = row.get("acf")
        values = {
            "slug": slug,
            "title": _rendered(row.get("title")),
            "content_html": _rendered(row.get("content")),
            # Keep the whole ACF blob: these pages carry contact details and
            # image sliders whose shape differs per page.
            "data": acf if isinstance(acf, dict) and acf else None,
        }
        if existing is None:
            if not dry:
                session.add(SitePage(wp_id=wp_id, **values))
            res.created += 1
        else:
            if not dry:
                for k, v in values.items():
                    setattr(existing, k, v)
            res.updated += 1
    return res


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="read WP, write nothing")
    ap.add_argument(
        "--only",
        choices=("blog", "neighborhoods", "pages"),
        help="import a single content type",
    )
    args = ap.parse_args()
    want = {args.only} if args.only else {"blog", "neighborhoods", "pages"}

    print(f"Source: {WP_BASE}")
    if args.dry_run:
        print("DRY RUN — nothing will be written\n")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        fetched: dict[str, list[dict[str, Any]]] = {}
        for name, path in (
            ("blog", "blog"),
            ("neighborhoods", "neighborhood"),
            ("pages", "pages"),
        ):
            if name in want:
                fetched[name] = await _fetch_all(client, path)
                print(f"  fetched {len(fetched[name]):3d} from WP /{path}")

    print()
    async with SessionLocal() as session:
        if "blog" in want:
            print((await import_blog(session, fetched["blog"], args.dry_run)).line("blog posts"))
        if "neighborhoods" in want:
            print(
                (
                    await import_neighborhoods(
                        session, fetched["neighborhoods"], args.dry_run
                    )
                ).line("neighborhoods")
            )
        if "pages" in want:
            r = await import_pages(session, fetched["pages"], args.dry_run)
            print(r.line("pages"))
            if r.skipped:
                print(f"    not found in WP: {', '.join(r.skipped)}")
        if not args.dry_run:
            await session.commit()

    await engine.dispose()
    print("\nDone." if not args.dry_run else "\nDry run complete — nothing written.")


if __name__ == "__main__":
    asyncio.run(main())
