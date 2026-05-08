"""Render newsletter emails (confirmation + new-property digest).

Pure functions. Returns (subject, html, text) so the email_client
sends both formats — plain-text fallback matters for clients that
strip HTML, and Resend serves both off a single send.

Two languages, EN + HE. Hebrew text is emitted right-to-left at the
container level via dir="rtl"; individual elements inherit. Property
formatting reuses the same conventions as `compose.py` so a digest
email reads consistently with what gets posted to social channels.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

from shmuel_backend.config import settings
from shmuel_backend.enums import PropertyType
from shmuel_backend.models import CloudPhoto, NewsletterSubscriber, Property


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _fmt_price(price: Decimal, currency: str) -> str:
    return f"{currency} {int(price):,}" if price == int(price) else f"{currency} {price:,.2f}"


def _type_label(prop_type: PropertyType, lang: str) -> str:
    if lang == "he":
        return "להשכרה" if prop_type == PropertyType.RENT else "למכירה"
    return "For rent" if prop_type == PropertyType.RENT else "For sale"


def _site_url() -> str:
    return settings.newsletter_site_base_url.rstrip("/")


def _api_url() -> str:
    return settings.newsletter_api_base_url.rstrip("/")


def confirmation_url(token: str) -> str:
    return f"{_api_url()}/public/newsletter/confirm/{quote(token)}"


def unsubscribe_url(token: str) -> str:
    return f"{_api_url()}/public/newsletter/unsubscribe/{quote(token)}"


def render_confirmation(sub: NewsletterSubscriber) -> RenderedEmail:
    confirm_link = confirmation_url(sub.confirmation_token)
    if sub.language == "he":
        subject = "אישור הרשמה — Classic Jerusalem Realty"
        text = (
            "תודה שנרשמת לרשימת התפוצה של Classic Jerusalem Realty.\n\n"
            "כדי להפעיל את ההרשמה, יש ללחוץ על הקישור הבא:\n"
            f"{confirm_link}\n\n"
            "אם לא ביקשת להירשם, ניתן להתעלם מהודעה זו."
        )
        html = _wrap_html(
            f"""<h2>אישור הרשמה</h2>
<p>תודה שנרשמת לרשימת התפוצה של Classic Jerusalem Realty.</p>
<p>כדי להפעיל את ההרשמה, יש ללחוץ על הקישור הבא:</p>
<p><a href="{confirm_link}" class="cta">אישור הרשמה</a></p>
<p class="muted">אם לא ביקשת להירשם, ניתן להתעלם מהודעה זו.</p>""",
            lang="he",
        )
    else:
        subject = "Confirm your subscription — Classic Jerusalem Realty"
        text = (
            "Thanks for signing up to Classic Jerusalem Realty's new-listings newsletter.\n\n"
            "Confirm your subscription:\n"
            f"{confirm_link}\n\n"
            "If you didn't request this, ignore this email."
        )
        html = _wrap_html(
            f"""<h2>Confirm your subscription</h2>
<p>Thanks for signing up to Classic Jerusalem Realty's new-listings newsletter.</p>
<p>Click below to confirm and start receiving emails when new properties are listed.</p>
<p><a href="{confirm_link}" class="cta">Confirm subscription</a></p>
<p class="muted">If you didn't request this, ignore this email.</p>""",
            lang="en",
        )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_digest(
    sub: NewsletterSubscriber,
    properties: list[Property],
    photos_by_property: dict,
) -> RenderedEmail:
    """Render the new-properties digest for one subscriber.

    `photos_by_property` maps property id -> list[CloudPhoto]. Only the
    first photo is used per card. Empty list is fine: card renders
    without an image.
    """
    lang = "he" if sub.language == "he" else "en"
    n = len(properties)
    site = _site_url()
    unsub_link = unsubscribe_url(sub.unsubscribe_token)

    if lang == "he":
        subject = f"{n} נכסים חדשים — Classic Jerusalem Realty"
        intro = f"<p>זה עתה הוספנו {n} נכסים חדשים. אלו ההצעות עבורכם:</p>"
        cta_label = "לצפייה באתר"
        unsub_label = "ביטול הרשמה"
    else:
        subject = f"{n} new properties — Classic Jerusalem Realty"
        intro = f"<p>We've just added {n} new properties. Here are the latest:</p>"
        cta_label = "View on the website"
        unsub_label = "Unsubscribe"

    cards_html = "\n".join(
        _card_html(p, photos_by_property.get(p.id, []), lang) for p in properties
    )

    body = f"""<h2>{subject}</h2>
{intro}
{cards_html}
<p style="margin-top:24px;"><a href="{site}" class="cta">{cta_label}</a></p>
<p class="muted footer">
  <a href="{unsub_link}">{unsub_label}</a>
</p>"""

    html = _wrap_html(body, lang=lang)
    text = _digest_plain_text(sub, properties, photos_by_property, lang=lang)
    return RenderedEmail(subject=subject, html=html, text=text)


def _card_html(prop: Property, photos: list[CloudPhoto], lang: str) -> str:
    type_label = _type_label(prop.type, lang)
    place = prop.neighborhood or prop.city or ""
    price = _fmt_price(prop.price, prop.currency)
    facts: list[str] = []
    if prop.rooms is not None:
        n = int(prop.rooms) if prop.rooms == int(prop.rooms) else float(prop.rooms)
        facts.append(f"{n} חדרים" if lang == "he" else f"{n} rooms")
    if prop.size_sqm:
        facts.append(f'{prop.size_sqm} מ"ר' if lang == "he" else f"{prop.size_sqm} sqm")
    facts_html = " · ".join(facts)

    photo_block = ""
    if photos:
        thumb = photos[0].thumbnail_url or photos[0].web_view_url
        if thumb:
            photo_block = (
                f'<img src="{thumb}" alt="" width="568" '
                'style="display:block;width:100%;max-width:568px;height:auto;'
                'border-top-left-radius:10px;border-top-right-radius:10px;" />'
            )

    badge_bg = "#17483b" if prop.type == PropertyType.RENT else "#b8893f"
    badge_html = (
        f'<span style="display:inline-block;background:{badge_bg};color:#fff;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;'
        f'padding:4px 10px;border-radius:999px;font-weight:600;">'
        f"{type_label}</span>"
    )

    inner_pad_top = "16px" if photo_block else "20px"
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:14px 0;background:#ffffff;border:1px solid #ece4d2;border-radius:10px;overflow:hidden;">
  <tr><td style="padding:0;">{photo_block}</td></tr>
  <tr><td style="padding:{inner_pad_top} 20px 18px 20px;">
    <div style="margin-bottom:8px;">{badge_html}</div>
    <div style="font-size:18px;font-weight:600;color:#2b2b2b;line-height:1.3;">{_html_escape(place)}</div>
    <div style="font-size:22px;font-weight:700;color:#17483b;margin:6px 0 4px;">{price}</div>
    <div style="color:#6c6c6c;font-size:14px;">{_html_escape(facts_html)}</div>
  </td></tr>
</table>"""


def _digest_plain_text(
    sub: NewsletterSubscriber,
    properties: list[Property],
    photos_by_property: dict,
    *,
    lang: str,
) -> str:
    lines: list[str] = []
    if lang == "he":
        lines.append(f"זה עתה הוספנו {len(properties)} נכסים חדשים:")
    else:
        lines.append(f"We've just added {len(properties)} new properties:")
    lines.append("")
    for p in properties:
        place = p.neighborhood or p.city or ""
        type_label = _type_label(p.type, lang)
        price = _fmt_price(p.price, p.currency)
        rooms = ""
        if p.rooms is not None:
            n = int(p.rooms) if p.rooms == int(p.rooms) else float(p.rooms)
            rooms = f" · {n} חדרים" if lang == "he" else f" · {n} rooms"
        size = ""
        if p.size_sqm:
            size = f' · {p.size_sqm} מ"ר' if lang == "he" else f" · {p.size_sqm} sqm"
        lines.append(f"- {place} — {type_label} — {price}{rooms}{size}")
    lines.append("")
    if lang == "he":
        lines.append(f"לצפייה באתר: {_site_url()}")
        lines.append(f"ביטול הרשמה: {unsubscribe_url(sub.unsubscribe_token)}")
    else:
        lines.append(f"View on the website: {_site_url()}")
        lines.append(f"Unsubscribe: {unsubscribe_url(sub.unsubscribe_token)}")
    return "\n".join(lines)


def _wrap_html(body: str, *, lang: str) -> str:
    direction = "rtl" if lang == "he" else "ltr"
    tagline = (
        "ברוכים הבאים לנדל\"ן בירושלים" if lang == "he"
        else "Jerusalem's local brokerage since 2008"
    )
    rights = (
        "© Classic Jerusalem Realty — כל הזכויות שמורות" if lang == "he"
        else "© Classic Jerusalem Realty — all rights reserved"
    )
    return f"""<!doctype html>
<html lang="{lang}" dir="{direction}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="color-scheme" content="light only" />
  <meta name="supported-color-schemes" content="light" />
  <title>Classic Jerusalem Realty</title>
  <style>
    body {{ margin:0; padding:0; background:#faf6ef;
            font-family: Georgia, "Times New Roman", serif;
            color:#2b2b2b; line-height:1.55; }}
    h1, h2, h3 {{ font-family: Georgia, "Times New Roman", serif; }}
    h2 {{ margin:0 0 12px; font-size:22px; color:#17483b; }}
    p {{ margin:0 0 12px; }}
    a {{ color:#17483b; }}
    a.cta {{ display:inline-block; padding:12px 24px;
             background:#17483b; color:#ffffff !important;
             text-decoration:none; border-radius:6px;
             font-weight:600; letter-spacing:0.02em;
             font-family: Helvetica, Arial, sans-serif; }}
    .muted {{ color:#6c6c6c; font-size:13px; }}
  </style>
</head>
<body style="margin:0;padding:0;background:#faf6ef;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#faf6ef;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;border:1px solid #ece4d2;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#17483b;padding:22px 28px;text-align:center;">
          <div style="font-family:Georgia,serif;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:0.04em;">Classic Jerusalem Realty</div>
          <div style="color:#d8c89c;font-size:12px;margin-top:4px;letter-spacing:0.08em;text-transform:uppercase;font-family:Helvetica,Arial,sans-serif;">{tagline}</div>
        </td></tr>
        <tr><td style="padding:28px 28px 24px 28px;">
{body}
        </td></tr>
        <tr><td style="background:#faf6ef;border-top:1px solid #ece4d2;padding:16px 28px;text-align:center;font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#8a8a8a;">
          {rights}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
