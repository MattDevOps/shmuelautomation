"""Post composition — turn a Property row into share-ready text.

Two languages: English (default) + Hebrew. Both are concise enough to fit a
WhatsApp status caption, longer than a Tweet. Numbers use thousand separators
in the property's currency. Photos contribute a single first-image URL when
available; multi-photo collages are out of scope for v1.
"""
from decimal import Decimal

from shmuel_backend.enums import PropertyType
from shmuel_backend.models import CloudPhoto, Property


def _fmt_price(price: Decimal, currency: str) -> str:
    return f"{currency} {int(price):,}" if price == int(price) else f"{currency} {price:,.2f}"


def _rooms_label(rooms: Decimal | None, lang: str) -> str:
    if rooms is None:
        return ""
    n = int(rooms) if rooms == int(rooms) else float(rooms)
    if lang == "he":
        return f"{n} חדרים"
    return f"{n} rooms"


def _type_label(prop_type: PropertyType, lang: str) -> str:
    if lang == "he":
        return "להשכרה" if prop_type == PropertyType.RENT else "למכירה"
    return "For rent" if prop_type == PropertyType.RENT else "For sale"


def compose_post(
    prop: Property, *, lang: str = "en", photos: list[CloudPhoto] | None = None
) -> str:
    type_label = _type_label(prop.type, lang)
    place = prop.neighborhood or prop.city
    if lang == "he" and place:
        headline = f"{type_label} ב{place}"
    elif place:
        headline = f"{type_label} — {place}"
    else:
        headline = type_label

    facts: list[str] = []
    rooms_str = _rooms_label(prop.rooms, lang)
    if rooms_str:
        facts.append(rooms_str)
    if prop.size_sqm:
        facts.append(f"{prop.size_sqm} מ\"ר" if lang == "he" else f"{prop.size_sqm} sqm")
    if prop.floor is not None:
        facts.append(f"קומה {prop.floor}" if lang == "he" else f"floor {prop.floor}")

    lines = [headline]
    if facts:
        lines.append(" · ".join(facts))
    lines.append(_fmt_price(prop.price, prop.currency))
    if prop.address:
        lines.append(prop.address)
    if prop.description:
        lines.append("")
        lines.append(prop.description.strip())

    if photos:
        first = photos[0]
        if first.web_view_url:
            lines.append("")
            lines.append(first.web_view_url)

    if prop.yad2_url:
        if not photos or not photos[0].web_view_url:
            lines.append("")
        lines.append(prop.yad2_url)

    return "\n".join(lines).strip()


def whatsapp_share_url(text: str, phone: str | None = None) -> str:
    """https://wa.me/{phone}?text={url-encoded} — phone optional, opens chat picker."""
    from urllib.parse import quote

    encoded = quote(text)
    if phone:
        digits = "".join(c for c in phone if c.isdigit())
        return f"https://wa.me/{digits}?text={encoded}"
    return f"https://wa.me/?text={encoded}"


def facebook_share_url(url: str) -> str:
    """FB sharer is URL-only; the text won't be pre-filled."""
    from urllib.parse import quote

    return f"https://www.facebook.com/sharer/sharer.php?u={quote(url, safe='')}"
