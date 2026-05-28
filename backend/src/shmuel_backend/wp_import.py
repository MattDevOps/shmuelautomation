"""Map WordPress property listings onto backend Property rows.

The public site's listings live in headless WordPress (the ACF
`properties` post type, served over the WP REST API). This module fetches
those listings and turns each one into the kwargs we need to create a
`Property`, plus the list of gallery photos to copy into Drive.

Everything here is pure / I/O-light so it can be unit-tested against
fixture dicts. The orchestration that actually writes to Postgres and
uploads to Drive lives in `scripts/import_wp_properties.py`.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import httpx

from shmuel_backend.config import settings
from shmuel_backend.enums import PropertyType

# WP category ids (resolved 2026-05; stable on this install). See the rebuild
# notes — the public frontend resolves these by slug, but for a one-time import
# the numeric ids are fine and avoid an extra round-trip.
SALE_CATEGORIES = {3, 7}  # for-sale, new-development
RENT_CATEGORIES = {9, 10, 11, 12}  # short-term, lt-furnished, lt-unfurnished, pesach/succot
SKIP_CATEGORIES = {1, 14}  # uncategorized, hide
FEATURED_CATEGORY = 13  # ambiguous — type inferred from ribbon text instead

# Stamped into Property.notes so re-running the import is idempotent: we skip
# any WP listing whose id already appears here.
_IMPORT_MARKER_RE = re.compile(r"\[wp-import id=(\d+)\]")

WP_LIST_FIELDS = ",".join(
    [
        "id",
        "slug",
        "link",
        "date",
        "title",
        "categories",
        "acf.details_properties",
        "acf.description",
        "acf.more_information",
        "acf.exclusivity",
        "acf.photo_gallery",
    ]
)


@dataclass
class PlannedPhoto:
    url: str
    file_name: str
    title: str | None = None


@dataclass
class PlannedProperty:
    """Everything needed to create one Property (+ its photos) from a WP row."""

    wp_id: int
    slug: str
    link: str
    kwargs: dict[str, object]
    photos: list[PlannedPhoto] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def import_marker(wp_id: int) -> str:
    return f"[wp-import id={wp_id}]"


def find_imported_wp_ids(notes_values: list[str | None]) -> set[int]:
    """Pull every already-imported WP id out of a batch of Property.notes."""
    ids: set[int] = set()
    for note in notes_values:
        if not note:
            continue
        ids.update(int(m) for m in _IMPORT_MARKER_RE.findall(note))
    return ids


def _details(row: dict) -> dict:
    return ((row.get("acf") or {}).get("details_properties") or {})


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    # ACF returns plain text but with HTML entities (&amp;, &#8217; …).
    text = html.unescape(value)
    return " ".join(text.split()).strip()


def _parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    # Keep digits and a single decimal point; drop ₪, commas, spaces, "NIS" etc.
    cleaned = re.sub(r"[^0-9.]", "", str(value))
    if not cleaned or cleaned == ".":
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("1"))
    except InvalidOperation:
        return None


def _parse_rooms(value: str | None) -> Decimal | None:
    if not value:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(value))
    if not m:
        return None
    try:
        rooms = Decimal(m.group(0))
    except InvalidOperation:
        return None
    # Property.rooms is Numeric(3,1): clamp to one decimal place, sane ceiling.
    rooms = rooms.quantize(Decimal("0.1"))
    return rooms if 0 <= rooms < Decimal("100") else None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def normalize_gallery(row: dict) -> list[dict]:
    """ACF returns photo_gallery either as a list or as a dict keyed '0','1',…"""
    gallery = ((row.get("acf") or {}).get("photo_gallery") or {}).get("photo_gallery")
    if isinstance(gallery, dict):
        return [v for v in gallery.values() if isinstance(v, dict)]
    if isinstance(gallery, list):
        return [v for v in gallery if isinstance(v, dict)]
    return []


def _best_photo_url(item: dict) -> str | None:
    direct = item.get("full_image_url")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    sizes = ((item.get("media_details") or {}).get("sizes") or {})
    for size in ("large", "medium_large", "full", "medium"):
        src = (sizes.get(size) or {}).get("source_url")
        if isinstance(src, str) and src.strip():
            return src.strip()
    return None


def _file_name_from_url(url: str, wp_id: int, index: int) -> str:
    tail = url.split("?")[0].rstrip("/").split("/")[-1]
    if tail and "." in tail:
        return tail
    return f"wp-{wp_id}-{index + 1}.jpg"


def is_available(row: dict) -> bool:
    """Available = not marked rented and not in the hide/uncategorized buckets."""
    cats = set(row.get("categories") or [])
    if cats & SKIP_CATEGORIES:
        return False
    return not _clean_text(_details(row).get("rented_day"))


def classify_type(row: dict) -> tuple[PropertyType, bool]:
    """Return (type, is_dual). `is_dual` marks listings offered for both
    rent and sale — we store them as their primary type and note the other.
    """
    cats = set(row.get("categories") or [])
    ribbon = _clean_text(_details(row).get("ribbon_cintillo")).lower()

    has_sale = bool(cats & SALE_CATEGORIES) or "sale" in ribbon
    has_rent = bool(cats & RENT_CATEGORIES) or "rent" in ribbon
    dual = has_sale and has_rent

    if has_sale and not has_rent:
        return PropertyType.SALE, dual
    if has_rent:
        # Dual listings: rent is the dominant intent across this catalogue.
        return PropertyType.RENT, dual
    # Featured-only / unclassified: lean on the ribbon, default to rent.
    if "sale" in ribbon:
        return PropertyType.SALE, dual
    return PropertyType.RENT, dual


def _build_description(row: dict) -> str | None:
    d = _details(row)
    acf = row.get("acf") or {}
    desc = acf.get("description") or {}
    parts: list[str] = []
    headline = _clean_text(d.get("property_name"))
    if headline:
        parts.append(headline)
    for key in ("paragraph_1", "paragraph_2"):
        p = _clean_text(desc.get(key))
        if p:
            parts.append(p)
    more = acf.get("more_information")
    if isinstance(more, list):
        for item in more:
            p = _clean_text(item if isinstance(item, str) else None)
            if p:
                parts.append(p)
    text = "\n\n".join(parts)
    return text or None


def _build_notes(row: dict, dual: bool, primary: PropertyType) -> str:
    d = _details(row)
    lines = [import_marker(int(row["id"]))]
    code = _clean_text(d.get("code_property"))
    if code:
        lines.append(f"WP code: {code}")
    lines.append(f"WP slug: {row.get('slug', '')}")
    if row.get("link"):
        lines.append(f"Source: {row['link']}")
    facts = []
    for label, key in (("Beds", "beds"), ("Baths", "baths"), ("Size", "sqm")):
        v = _clean_text(d.get(key))
        if v:
            facts.append(f"{label}: {v}{' sqm' if key == 'sqm' else ''}")
    if facts:
        lines.append(" · ".join(facts))
    ribbon = _clean_text(d.get("ribbon_cintillo"))
    if ribbon:
        lines.append(f"WP ribbon: {ribbon}")
    if dual:
        other = "sale" if primary == PropertyType.RENT else "rent"
        lines.append(f"Note: also listed for {other} on the website.")
    return "\n".join(lines)


def build_planned(row: dict, *, max_photos: int | None = None) -> PlannedProperty | None:
    """Turn one WP property row into a PlannedProperty, or None if it should
    be skipped (rented / hidden / uncategorized / no price)."""
    if not is_available(row):
        return None

    wp_id = int(row["id"])
    d = _details(row)
    ptype, dual = classify_type(row)
    warnings: list[str] = []

    price = _parse_decimal(d.get("price_shekels"))
    if price is None or price <= 0:
        # Price is required on Property and central to every downstream
        # feature (queue, chatbot, newsletter). Skip price-less rows.
        return None

    neighborhood = (
        _clean_text(d.get("neighborhood_selector"))
        or _clean_text(d.get("neighborhood"))
        or None
    )
    address = _clean_text(d.get("street_name")) or None

    kwargs: dict[str, object] = {
        "type": ptype,
        "price": price,
        "currency": "ILS",
        "rooms": _parse_rooms(d.get("beds")),
        "size_sqm": _parse_int(d.get("sqm")),
        "neighborhood": neighborhood[:200] if neighborhood else None,
        "address": address[:500] if address else None,
        "city": "Jerusalem",
        "description": _build_description(row),
        "notes": _build_notes(row, dual, ptype),
    }

    photos: list[PlannedPhoto] = []
    for i, item in enumerate(normalize_gallery(row)):
        url = _best_photo_url(item)
        if not url:
            continue
        photos.append(
            PlannedPhoto(
                url=url,
                file_name=_file_name_from_url(url, wp_id, i),
                title=_clean_text(item.get("title")) or None,
            )
        )
    if max_photos is not None and max_photos >= 0:
        photos = photos[:max_photos]
    if not photos:
        warnings.append("no photos in WP gallery")

    return PlannedProperty(
        wp_id=wp_id,
        slug=str(row.get("slug") or ""),
        link=str(row.get("link") or ""),
        kwargs=kwargs,
        photos=photos,
        warnings=warnings,
    )


async def fetch_all_properties(client: httpx.AsyncClient) -> list[dict]:
    """Page through every WP property (100/page) with the fields we map."""
    base = settings.wp_rest_base.rstrip("/")
    rows: list[dict] = []
    page = 1
    while True:
        r = await client.get(
            f"{base}/properties",
            params={"per_page": 100, "page": page, "_fields": WP_LIST_FIELDS},
        )
        if r.status_code == 400:
            # WP returns 400 ("rest_post_invalid_page_number") past the last page.
            break
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        total_pages = int(r.headers.get("x-wp-totalpages", "1") or "1")
        if page >= total_pages:
            break
        page += 1
    return rows


def build_plan(rows: list[dict], *, max_photos: int | None = None) -> list[PlannedProperty]:
    planned: list[PlannedProperty] = []
    for row in rows:
        p = build_planned(row, max_photos=max_photos)
        if p is not None:
            planned.append(p)
    return planned
