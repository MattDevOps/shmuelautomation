import asyncio
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from shmuel_backend.config import settings

YAD2_HOST_SUFFIX = "yad2.co.il"
FETCH_TIMEOUT = 12.0
FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = 1.5

# Yad2 sits behind ShieldSquare (Radware) bot protection. From a datacenter IP
# (e.g. Cloud Run) a normal desktop User-Agent gets served a JS captcha page
# instead of the listing, so no property data can be parsed. We identify as the
# Facebook link-preview crawler: ShieldSquare lets Open Graph fetches through so
# WhatsApp/Facebook unfurls keep working, and OG tags are exactly what we parse.
USER_AGENT = (
    "facebookexternalhit/1.1 "
    "(+http://www.facebook.com/externalhit_uatext.php)"
)

# Default headers that look like a real link-preview fetch rather than a bare
# scraper. Helps with UA/header-gated rules on the way to the OG-tagged page.
FETCH_HEADERS = {
    "user-agent": USER_AGENT,
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "he,en;q=0.8",
    "cache-control": "no-cache",
}

# Fingerprints of the ShieldSquare / generic anti-bot challenge page. When the
# response is one of these we got blocked, not an empty listing — the
# distinction matters because the two cases need different user guidance.
_CHALLENGE_MARKERS = (
    "shieldsquare",
    "ssjsinternal",
    "px-captcha",
    "perimeterx",
    "validate.perfdrive",
    "are you a human",
    "/cdn-cgi/challenge-platform",
)


class Yad2Error(Exception):
    pass


class Yad2Blocked(Yad2Error):
    """Yad2's bot protection served a challenge instead of the listing."""


def _looks_like_challenge(html: str) -> bool:
    head = html[:4000].lower()
    # An OG-tagged listing is never a challenge page, even if a marker word
    # happens to appear deeper in analytics scripts.
    if "og:title" in head:
        return False
    return any(marker in head for marker in _CHALLENGE_MARKERS)


@dataclass
class Yad2Preview:
    url: str
    title: str | None = None
    description: str | None = None
    price: str | None = None
    rooms: str | None = None
    size_sqm: int | None = None
    floor: int | None = None
    address: str | None = None
    neighborhood: str | None = None
    image_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_yad2_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host == YAD2_HOST_SUFFIX or host.endswith("." + YAD2_HOST_SUFFIX)


async def fetch_yad2_html(url: str) -> str:
    # Optional egress proxy (residential IP or scraping API). When set it lets
    # the fetch originate from an IP Yad2's bot protection trusts, which a bare
    # Cloud Run datacenter IP is not. No-op when blank (default).
    proxy = settings.yad2_fetch_proxy or None
    last_challenge: Yad2Blocked | None = None
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers=FETCH_HEADERS,
        proxy=proxy,
    ) as client:
        for attempt in range(FETCH_ATTEMPTS):
            r = await client.get(url)
            if r.status_code >= 400:
                raise Yad2Error(f"yad2 returned status {r.status_code}")
            if _looks_like_challenge(r.text):
                # Challenges are probabilistic; a retry often gets through.
                last_challenge = Yad2Blocked(
                    "yad2 served a bot-protection challenge"
                )
                if attempt + 1 < FETCH_ATTEMPTS:
                    await asyncio.sleep(FETCH_BACKOFF_SECONDS)
                continue
            return r.text
    raise last_challenge or Yad2Blocked("yad2 served a bot-protection challenge")


def parse_yad2_html(url: str, html: str) -> Yad2Preview:
    soup = BeautifulSoup(html, "html.parser")
    preview = Yad2Preview(url=url)

    # __NEXT_DATA__ is the authoritative source — it carries the full structured
    # listing (price, sqm, floor, address, whole photo gallery). Open Graph only
    # exposes a title and a single image, and Yad2 ships no JSON-LD, so without
    # this every numeric field came back blank and only one photo was found.
    _apply_next_data(soup, preview)
    # OG fills the human-friendly title + description that NEXT_DATA lacks, and
    # is the photo fallback when the embedded JSON is missing/changed shape.
    _apply_open_graph(soup, preview)
    _apply_json_ld(soup, preview)
    _apply_text_heuristics(preview)

    if not any(
        (preview.title, preview.description, preview.price, preview.image_urls)
    ):
        preview.warnings.append(
            "Could not extract any property data from the page — fill in manually."
        )
    return preview


def _apply_next_data(soup: BeautifulSoup, preview: Yad2Preview) -> None:
    """Extract the structured listing from Yad2's embedded Next.js payload.

    Yad2 listing pages ship the entire ad as JSON in `<script id="__NEXT_DATA__">`
    under `props.pageProps.dehydratedState.queries[].state.data`. That object
    holds price, square meters, floor, full street address and the complete
    photo gallery — none of which survive in Open Graph tags. We locate the
    listing query by its shape (a data dict carrying `metaData`) so we don't
    depend on the exact query-key string.
    """
    tag = soup.find("script", id="__NEXT_DATA__")
    raw = tag.string if tag else None
    if not raw:
        return
    try:
        root = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    data = _find_listing_data(root, preview.url)
    if data is None:
        return

    details = data.get("additionalDetails")
    details = details if isinstance(details, dict) else {}
    address = data.get("address")
    address = address if isinstance(address, dict) else {}

    price = data.get("price")
    if not preview.price and isinstance(price, (int, float)) and price > 0:
        preview.price = str(int(price))

    sqm = details.get("squareMeter")
    if preview.size_sqm is None and isinstance(sqm, (int, float)) and sqm > 0:
        preview.size_sqm = int(sqm)

    rooms = details.get("roomsCount")
    if not preview.rooms and isinstance(rooms, (int, float)) and rooms > 0:
        preview.rooms = _fmt_number(rooms)

    house = address.get("house")
    house = house if isinstance(house, dict) else {}
    floor = house.get("floor")
    # bool is a subclass of int — exclude it so a stray JSON true isn't read as 1.
    if preview.floor is None and isinstance(floor, int) and not isinstance(floor, bool):
        # floor 0 is the ground floor — a legitimate value, so guard on None.
        preview.floor = floor

    if not preview.address:
        street = _text_of(address.get("street"))
        number = _house_number(house.get("number"))
        if street and number:
            preview.address = f"{street} {number}"
        elif street:
            preview.address = street

    if not preview.neighborhood:
        neighborhood = _text_of(address.get("neighborhood"))
        if neighborhood:
            preview.neighborhood = neighborhood

    if not preview.image_urls:
        meta = data.get("metaData")
        meta = meta if isinstance(meta, dict) else {}
        images = meta.get("images")
        if isinstance(images, list):
            preview.image_urls = [u for u in images if isinstance(u, str) and u]
        if not preview.image_urls:
            cover = meta.get("coverImage")
            if isinstance(cover, str) and cover:
                preview.image_urls = [cover]


def _find_listing_data(root: object, url: str) -> dict | None:
    """Walk to the dehydrated query whose data is THIS listing.

    A listing page can dehydrate several queries that carry `metaData` (the ad
    itself plus "similar listings" carousels). Picking the first one risks
    parsing a different property's price/photos. So we prefer the query whose
    token/key matches the item token in the page URL, and only fall back to the
    first metaData-bearing query when no token match is found.
    """
    try:
        queries = root["props"]["pageProps"]["dehydratedState"]["queries"]
    except (KeyError, TypeError):
        return None
    if not isinstance(queries, list):
        return None

    candidates: list[dict] = []
    for query in queries:
        if not isinstance(query, dict):
            continue
        state = query.get("state")
        data = state.get("data") if isinstance(state, dict) else None
        if not isinstance(data, dict) or "metaData" not in data:
            continue
        candidates.append(data)
        token = data.get("token")
        if isinstance(token, str) and token and token in url:
            return data
        key = query.get("queryKey")
        if isinstance(key, list) and any(
            isinstance(k, str) and k and k in url for k in key
        ):
            return data
    return candidates[0] if candidates else None


def _house_number(value: object) -> str | None:
    """Normalize a house number, allowing letter suffixes ('8', '8א')."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _text_of(node: object) -> str | None:
    """Pull the Hebrew display label out of a Yad2 `{id, text}` node."""
    if isinstance(node, dict):
        text = node.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _fmt_number(value: int | float) -> str:
    """Render 3 as '3' and 3.5 as '3.5' (rooms can be half-integers)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _apply_open_graph(soup: BeautifulSoup, preview: Yad2Preview) -> None:
    og_images: list[str] = []
    for tag in soup.find_all("meta", property=True):
        prop = tag.get("property", "")
        content = tag.get("content")
        if not content:
            continue
        if prop == "og:title" and not preview.title:
            # Yad2 appends a site tagline after a pipe ("... | אלפי מודעות
            # חדשות בכל יום!") — drop it so only the listing title remains.
            preview.title = content.split("|", 1)[0].strip()
        elif prop == "og:description" and not preview.description:
            preview.description = content.strip()
        elif prop == "og:image" and content not in og_images:
            og_images.append(content)
    # Only fall back to the OG images when NEXT_DATA gave us no gallery —
    # otherwise the single og:image is just a near-dup of the full set.
    if not preview.image_urls:
        preview.image_urls = og_images


def _apply_json_ld(soup: BeautifulSoup, preview: Yad2Preview) -> None:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _iter_ld_nodes(data):
            if not isinstance(node, dict):
                continue
            offers = node.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price")
                if price is not None and not preview.price:
                    preview.price = str(price)
            address = node.get("address")
            if isinstance(address, dict):
                locality = address.get("addressLocality")
                street = address.get("streetAddress")
                if locality and not preview.neighborhood:
                    preview.neighborhood = str(locality)
                if street and not preview.address:
                    preview.address = str(street)


def _iter_ld_nodes(data: object) -> list[object]:
    if isinstance(data, list):
        out: list[object] = []
        for item in data:
            out.extend(_iter_ld_nodes(item))
        return out
    if isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            return _iter_ld_nodes(graph)
        return [data]
    return []


_PRICE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:₪|ש[״\"']ח|NIS|ILS)", re.IGNORECASE)
_ROOMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:חדר|חדרים|rooms?)", re.IGNORECASE)
_SQM_RE = re.compile(r"(\d{2,4})\s*(?:מ[״\"']ר|sqm|m2|m²)", re.IGNORECASE)


def _apply_text_heuristics(preview: Yad2Preview) -> None:
    blob_parts = [preview.title or "", preview.description or ""]
    blob = " ".join(p for p in blob_parts if p)
    if not blob:
        return

    if not preview.price:
        m = _PRICE_RE.search(blob)
        if m:
            preview.price = m.group(1).replace(",", "")
    if not preview.rooms:
        m = _ROOMS_RE.search(blob)
        if m:
            preview.rooms = m.group(1)
    if not preview.size_sqm:
        m = _SQM_RE.search(blob)
        if m:
            preview.size_sqm = int(m.group(1))
