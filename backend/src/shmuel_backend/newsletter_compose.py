"""Render newsletter emails (confirmation + new-property digest).

Pure functions. Returns (subject, html, text) so the email_client
sends both formats — plain-text fallback matters for clients that
strip HTML, and Resend serves both off a single send.

Two languages, EN + HE. Hebrew text is emitted right-to-left at the
container level via dir="rtl"; individual elements inherit. Property
formatting reuses the same conventions as `compose.py` so a digest
email reads consistently with what gets posted to social channels.

HTML is table-based and uses inline styles for compatibility with
Outlook desktop (Word rendering engine), Gmail web/iOS/Android,
Apple Mail, Yahoo, and ProtonMail. No flexbox, no CSS grid, no
absolute positioning, no background-image (Outlook strips it).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote, urlencode

from shmuel_backend.config import settings
from shmuel_backend.enums import PropertyType
from shmuel_backend.models import CloudPhoto, NewsletterSubscriber, Property

# --- Brand constants -------------------------------------------------
BRAND_NAME = "Classic Jerusalem Realty"
BRAND_GREEN = "#17483b"      # primary brand
BRAND_GREEN_DK = "#0f342a"   # header darker
BRAND_GOLD = "#b8893f"       # secondary accent
BRAND_GOLD_LT = "#d8c89c"    # tagline / soft accent
PAPER = "#faf6ef"            # body background (warm cream)
INK = "#23241f"              # primary text
INK_MUTED = "#6c6c6c"        # secondary text
HAIRLINE = "#ece4d2"         # warm divider
CARD_BG = "#ffffff"

CONTACT_PHONE = "+972-58-654-0969"
CONTACT_PHONE_TEL = "+97258654-0969"
CONTACT_EMAIL = "classicjerusaleminfo@gmail.com"
CONTACT_ADDRESS_EN = "Jerusalem, Israel"
CONTACT_ADDRESS_HE = "ירושלים, ישראל"


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


def _per_month_suffix(prop_type: PropertyType, lang: str) -> str:
    """Append a /mo to rent prices so the cadence is obvious. Sales: no suffix."""
    if prop_type != PropertyType.RENT:
        return ""
    return " / חודש" if lang == "he" else " / mo"


def _site_url() -> str:
    return settings.newsletter_site_base_url.rstrip("/")


def _api_url() -> str:
    return settings.newsletter_api_base_url.rstrip("/")


def confirmation_url(token: str) -> str:
    return f"{_api_url()}/public/newsletter/confirm/{quote(token)}"


def unsubscribe_url(token: str) -> str:
    return f"{_api_url()}/public/newsletter/unsubscribe/{quote(token)}"


def _property_url(prop: Property, lang: str) -> str:
    """Per-card click-through URL.

    The backend's Property doesn't carry the public-site slug (those live in
    WordPress), so we link to the type-filtered listing page with the
    neighborhood pre-applied. The lead lands on a curated list of similar
    inventory, not a 404. Locale-prefixed when not English.
    """
    base = _site_url()
    locale_prefix = "" if lang == "en" else f"/{lang}"
    section = "sell" if prop.type == PropertyType.SALE else "rent"
    qs = ""
    if prop.neighborhood:
        qs = "?" + urlencode({"neighborhood": prop.neighborhood})
    return f"{base}{locale_prefix}/{section}/{qs}"


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
<p>{_cta_button(confirm_link, "אישור הרשמה")}</p>
<p class="muted">אם לא ביקשת להירשם, ניתן להתעלם מהודעה זו.</p>""",
            lang="he",
            sub=sub,
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
<p>{_cta_button(confirm_link, "Confirm subscription")}</p>
<p class="muted">If you didn't request this, ignore this email.</p>""",
            lang="en",
            sub=sub,
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
    locale_prefix = "" if lang == "en" else f"/{lang}"

    if lang == "he":
        subject = f"{n} נכסים חדשים בירושלים"
        eyebrow = "נכסים חדשים השבוע"
        headline = f"{n} נכסים חדשים זמינים כעת"
        intro = (
            "אספנו עבורכם את הנכסים האחרונים שנכנסו לרשימה. "
            "לחצו על כל נכס לעיון בפרטים ולהוספת פגישת ביקור."
        )
        browse_label = "לכל הנכסים באתר"
    else:
        subject = f"{n} new Jerusalem properties this week"
        eyebrow = "New listings"
        headline = f"{n} new properties just listed"
        intro = (
            "We've gathered the latest inventory we've added. "
            "Tap any listing to see details and book a viewing."
        )
        browse_label = "Browse all properties"

    cards_html = "\n".join(
        _card_html(p, photos_by_property.get(p.id, []), lang) for p in properties
    )

    body = f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="padding:0 0 4px;font-family:Helvetica,Arial,sans-serif;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:{BRAND_GOLD};font-weight:600;">{eyebrow}</td></tr>
  <tr><td style="padding:0 0 10px;font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.2;color:{BRAND_GREEN};font-weight:700;">{headline}</td></tr>
  <tr><td style="padding:0 0 18px;font-family:Georgia,serif;font-size:15px;line-height:1.6;color:{INK};">{intro}</td></tr>
</table>
{cards_html}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td align="center" style="padding:26px 0 6px;">{_cta_button(f"{site}{locale_prefix}/", browse_label)}</td></tr>
</table>"""

    html = _wrap_html(body, lang=lang, sub=sub)
    text = _digest_plain_text(sub, properties, photos_by_property, lang=lang)
    return RenderedEmail(subject=subject, html=html, text=text)


def _card_html(prop: Property, photos: list[CloudPhoto], lang: str) -> str:
    type_label = _type_label(prop.type, lang).upper()
    badge_bg = BRAND_GREEN if prop.type == PropertyType.RENT else BRAND_GOLD

    # Title line: NEIGHBORHOOD (uppercase, letter-spaced) over street address.
    neighborhood = (prop.neighborhood or prop.city or "").strip()
    street = (prop.address or "").strip()

    # Price with per-month suffix for rentals.
    price = _fmt_price(prop.price, prop.currency) + _per_month_suffix(prop.type, lang)

    # Feature line: rooms, baths (not in model — skip), floor, sqm.
    bits: list[str] = []
    if prop.rooms is not None:
        n = int(prop.rooms) if prop.rooms == int(prop.rooms) else float(prop.rooms)
        bits.append(f"{n} חדרים" if lang == "he" else f"{n} BD")
    if prop.size_sqm:
        bits.append(f'{prop.size_sqm} מ"ר' if lang == "he" else f"{prop.size_sqm} sqm")
    if prop.floor is not None:
        bits.append(
            f"קומה {prop.floor}" if lang == "he"
            else f"floor {prop.floor}"
        )
    facts_line = "  ·  ".join(bits)

    # Description excerpt: trimmed to ~160 chars on a word boundary so the
    # card doesn't become a wall of text. Shmuel fills these in via the
    # Properties admin page; if the field is empty we skip the line cleanly.
    description_excerpt = _excerpt(prop.description, max_chars=180)

    cta_label = "צפייה בנכסים דומים" if lang == "he" else "View similar properties"
    cta_url = _property_url(prop, lang)

    photo_block = ""
    if photos:
        thumb = photos[0].thumbnail_url or photos[0].web_view_url
        if thumb:
            photo_block = f"""<tr>
  <td style="padding:0;background:{HAIRLINE};line-height:0;">
    <img src="{_html_escape_attr(thumb)}" alt="" width="556"
         style="display:block;width:100%;max-width:556px;height:auto;
                border:0;outline:0;border-top-left-radius:12px;border-top-right-radius:12px;" />
  </td>
</tr>"""

    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin:0 0 18px;background:{CARD_BG};border:1px solid {HAIRLINE};
              border-radius:12px;overflow:hidden;">
  {photo_block}
  <tr><td style="padding:20px 22px 22px 22px;">
    <div style="font-family:Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:0.1em;
                color:#fff;font-weight:700;background:{badge_bg};display:inline-block;
                padding:5px 12px;border-radius:4px;">{type_label}</div>
    <div style="font-family:Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:0.18em;
                color:{BRAND_GOLD};font-weight:700;text-transform:uppercase;
                margin:14px 0 2px;">{_html_escape(neighborhood)}</div>
    {('<div style="font-family:Georgia,serif;font-size:18px;color:' + INK
      + ';font-weight:600;line-height:1.3;">' + _html_escape(street) + '</div>') if street else ''}
    <div style="font-family:Georgia,serif;font-size:26px;color:{BRAND_GREEN};
                font-weight:700;line-height:1.2;margin:10px 0 6px;">{_html_escape(price)}</div>
    {('<div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:' + INK_MUTED
      + ';letter-spacing:0.04em;margin-bottom:14px;">' + _html_escape(facts_line) + '</div>')
      if facts_line else '<div style="height:8px;line-height:0;font-size:0;">&nbsp;</div>'}
    {('<div style="font-family:Georgia,serif;font-size:14px;color:' + INK
      + ';line-height:1.6;margin-bottom:18px;">' + _html_escape(description_excerpt) + '</div>')
      if description_excerpt else ''}
    <div>{_cta_button(cta_url, cta_label, size="sm")}</div>
  </td></tr>
</table>"""


def _cta_button(href: str, label: str, *, size: str = "md") -> str:
    """Email-safe CTA button via inline-styled anchor. Outlook ignores
    border-radius but we have a clear background so the box still reads.
    """
    pad = "10px 18px" if size == "sm" else "14px 28px"
    font = "13px" if size == "sm" else "15px"
    return (
        f'<a href="{_html_escape_attr(href)}" target="_blank" '
        f'style="display:inline-block;padding:{pad};background:{BRAND_GREEN};'
        f'color:#ffffff !important;text-decoration:none;border-radius:6px;'
        f'font-family:Helvetica,Arial,sans-serif;font-size:{font};font-weight:600;'
        f'letter-spacing:0.04em;border:0;">{_html_escape(label)}</a>'
    )


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
        street = p.address or ""
        type_label = _type_label(p.type, lang)
        price = _fmt_price(p.price, p.currency) + _per_month_suffix(p.type, lang)
        rooms = ""
        if p.rooms is not None:
            n = int(p.rooms) if p.rooms == int(p.rooms) else float(p.rooms)
            rooms = f" · {n} חדרים" if lang == "he" else f" · {n} BD"
        size = ""
        if p.size_sqm:
            size = f' · {p.size_sqm} מ"ר' if lang == "he" else f" · {p.size_sqm} sqm"
        title = f"{place}{' — ' + street if street else ''}"
        lines.append(f"- {title} — {type_label} — {price}{rooms}{size}")
        lines.append(f"  {_property_url(p, lang)}")
    lines.append("")
    if lang == "he":
        lines.append(f"לכל הנכסים: {_site_url()}")
        lines.append(f"טלפון: {CONTACT_PHONE}")
        lines.append(f"דוא\"ל: {CONTACT_EMAIL}")
        lines.append(f"ביטול הרשמה: {unsubscribe_url(sub.unsubscribe_token)}")
    else:
        lines.append(f"Browse all properties: {_site_url()}")
        lines.append(f"Phone: {CONTACT_PHONE}")
        lines.append(f"Email: {CONTACT_EMAIL}")
        lines.append(f"Unsubscribe: {unsubscribe_url(sub.unsubscribe_token)}")
    return "\n".join(lines)


def _wrap_html(body: str, *, lang: str, sub: NewsletterSubscriber | None = None) -> str:
    direction = "rtl" if lang == "he" else "ltr"
    tagline = (
        "תיווך מקומי בירושלים מאז 2008" if lang == "he"
        else "Jerusalem's local brokerage since 2008"
    )
    address = CONTACT_ADDRESS_HE if lang == "he" else CONTACT_ADDRESS_EN
    rights = (
        f"© {BRAND_NAME} — כל הזכויות שמורות" if lang == "he"
        else f"© {BRAND_NAME} — all rights reserved"
    )
    unsub_label = "ביטול הרשמה" if lang == "he" else "Unsubscribe"
    unsub_link = unsubscribe_url(sub.unsubscribe_token) if sub else "#"

    contact_label_phone = "טלפון" if lang == "he" else "Phone"
    contact_label_email = "דוא\"ל" if lang == "he" else "Email"

    # Header monogram (Unicode-only, no emoji). The "CJ" mark gives the
    # header an identifiable wordmark even in dark-mode inboxes that
    # strip background colors.
    monogram = "CJ"

    return f"""<!doctype html>
<html lang="{lang}" dir="{direction}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="color-scheme" content="light only" />
  <meta name="supported-color-schemes" content="light" />
  <title>{BRAND_NAME}</title>
  <style>
    body {{ margin:0; padding:0; background:{PAPER};
            font-family: Georgia, "Times New Roman", serif;
            color:{INK}; line-height:1.55; -webkit-text-size-adjust:100%;
            -ms-text-size-adjust:100%; }}
    h1, h2, h3 {{ font-family: Georgia, "Times New Roman", serif; margin:0; }}
    h2 {{ font-size:22px; color:{BRAND_GREEN}; }}
    p {{ margin:0 0 12px; }}
    a {{ color:{BRAND_GREEN}; }}
    .muted {{ color:{INK_MUTED}; font-size:13px; }}
    @media only screen and (max-width: 620px) {{
      .container {{ width:100% !important; }}
      .pad-x {{ padding-left:18px !important; padding-right:18px !important; }}
      .hide-mobile {{ display:none !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:{PAPER};">
  <!--[if mso]><table role="presentation" width="600" align="center"><tr><td><![endif]-->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:{PAPER};">
    <tr><td align="center" style="padding:28px 12px 36px;">
      <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;background:{CARD_BG};border:1px solid {HAIRLINE};
                    border-radius:14px;overflow:hidden;">
        <!-- Header -->
        <tr><td style="background:{BRAND_GREEN_DK};padding:0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td class="pad-x" style="padding:20px 28px;vertical-align:middle;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td style="vertical-align:middle;padding-{('left' if direction == 'rtl' else 'right')}:14px;">
                      <div style="width:46px;height:46px;background:{BRAND_GOLD};
                                  border-radius:50%;text-align:center;line-height:46px;
                                  font-family:Georgia,serif;font-weight:700;font-size:18px;
                                  color:{BRAND_GREEN_DK};letter-spacing:0.04em;">{monogram}</div>
                    </td>
                    <td style="vertical-align:middle;">
                      <div style="font-family:Georgia,serif;color:#ffffff;font-size:20px;
                                  font-weight:700;letter-spacing:0.04em;">{BRAND_NAME}</div>
                      <div style="color:{BRAND_GOLD_LT};font-size:11px;margin-top:3px;
                                  letter-spacing:0.1em;text-transform:uppercase;
                                  font-family:Helvetica,Arial,sans-serif;">{tagline}</div>
                    </td>
                  </tr>
                </table>
              </td>
              <td class="hide-mobile" align="{'left' if direction == 'rtl' else 'right'}"
                  style="padding:20px 28px;vertical-align:middle;
                         font-family:Helvetica,Arial,sans-serif;font-size:12px;">
                <a href="tel:{_html_escape_attr(CONTACT_PHONE_TEL)}"
                   style="color:{BRAND_GOLD_LT};text-decoration:none;letter-spacing:0.04em;">
                  {_html_escape(CONTACT_PHONE)}
                </a>
              </td>
            </tr>
          </table>
        </td></tr>

        <!-- Body -->
        <tr><td class="pad-x" style="padding:30px 28px 24px;">
{body}
        </td></tr>

        <!-- Footer -->
        <tr><td style="background:{PAPER};border-top:1px solid {HAIRLINE};
                       padding:22px 28px 24px;text-align:center;
                       font-family:Helvetica,Arial,sans-serif;font-size:12px;color:{INK_MUTED};">
          <div style="font-family:Georgia,serif;color:{BRAND_GREEN};font-size:14px;
                      font-weight:700;letter-spacing:0.04em;margin-bottom:6px;">{BRAND_NAME}</div>
          <div style="margin-bottom:4px;">
            {contact_label_phone}:
            <a href="tel:{_html_escape_attr(CONTACT_PHONE_TEL)}"
               style="color:{BRAND_GREEN};text-decoration:none;">{_html_escape(CONTACT_PHONE)}</a>
            &nbsp;·&nbsp;
            {contact_label_email}:
            <a href="mailto:{CONTACT_EMAIL}" style="color:{BRAND_GREEN};text-decoration:none;">{CONTACT_EMAIL}</a>
          </div>
          <div style="margin-bottom:12px;">{address}</div>
          <div style="margin-bottom:10px;">{rights}</div>
          <div>
            <a href="{_html_escape_attr(unsub_link)}"
               style="color:{INK_MUTED};text-decoration:underline;font-size:11px;">{unsub_label}</a>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
  <!--[if mso]></td></tr></table><![endif]-->
</body>
</html>"""


def _excerpt(text: str | None, *, max_chars: int = 180) -> str:
    """Return a single-line excerpt no longer than `max_chars`, trimmed on
    a word boundary with a trailing ellipsis when truncated.

    `Property.description` may contain newlines (Shmuel types multi-paragraph
    notes); we collapse whitespace so the card line stays compact.
    """
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    cut = flat[: max_chars + 1].rsplit(" ", 1)[0].rstrip(",.;:—-")
    return f"{cut}…"


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_escape_attr(s: str) -> str:
    # Same as _html_escape today; kept separate so we can tighten attr
    # escaping (e.g. strip newlines for header injection) without
    # affecting body text rendering.
    return _html_escape(s)
