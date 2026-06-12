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


def _apply_open_graph(soup: BeautifulSoup, preview: Yad2Preview) -> None:
    for tag in soup.find_all("meta", property=True):
        prop = tag.get("property", "")
        content = tag.get("content")
        if not content:
            continue
        if prop == "og:title" and not preview.title:
            preview.title = content.strip()
        elif prop == "og:description" and not preview.description:
            preview.description = content.strip()
        elif prop == "og:image" and content not in preview.image_urls:
            preview.image_urls.append(content)


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
