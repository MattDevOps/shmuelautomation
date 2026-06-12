"""Build a share-ready photo collage for a property.

Lays up to four property photos into a square canvas (a single image, a 1x2
split, or a 2x2 grid) and overlays the Classic Jerusalem logo centered on a
soft card so it stays legible over any photo. Output is PNG bytes, sized for
WhatsApp (1080x1080 by default).

Pure image math — no I/O beyond reading the bundled logo. The caller fetches
the photo bytes (from Drive) and hands them in.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

CANVAS = 1080
GUTTER = 8  # px between tiles
BRAND_BG = (15, 30, 54)  # deep navy, shown only when a tile is missing
LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

# Logo sizing/backing, as fractions of the canvas.
_LOGO_WIDTH_FRAC = 0.30
_CARD_PAD_FRAC = 0.035


class CollageError(ValueError):
    """Raised when there isn't enough material to build a collage."""


def _tile_rects(n: int) -> list[tuple[int, int, int, int]]:
    """Pixel boxes (left, top, right, bottom) for `n` tiles (1, 2, 3, or 4)."""
    c = CANVAS
    g = GUTTER
    mid = c // 2
    if n <= 1:
        return [(0, 0, c, c)]
    if n == 2:
        # Side by side.
        return [(0, 0, mid - g // 2, c), (mid + g // 2, 0, c, c)]
    # 3 and 4 both use a 2x2 grid; with 3 photos the 4th cell is brand fill.
    return [
        (0, 0, mid - g // 2, mid - g // 2),
        (mid + g // 2, 0, c, mid - g // 2),
        (0, mid + g // 2, mid - g // 2, c),
        (mid + g // 2, mid + g // 2, c, c),
    ]


def _load(photo: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(photo))
        img.load()
        return img.convert("RGB")
    except Exception:
        # A corrupt / non-image blob shouldn't sink the whole collage.
        return None


def _logo_overlay(canvas: Image.Image) -> None:
    if not LOGO_PATH.exists():
        return
    logo = Image.open(LOGO_PATH).convert("RGBA")
    target_w = int(CANVAS * _LOGO_WIDTH_FRAC)
    scale = target_w / logo.width
    logo = logo.resize((target_w, int(logo.height * scale)), Image.LANCZOS)

    pad = int(CANVAS * _CARD_PAD_FRAC)
    card_w, card_h = logo.width + pad * 2, logo.height + pad * 2
    cx, cy = CANVAS // 2, CANVAS // 2

    # Soft translucent white card so the logo reads over any photo.
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    radius = int(min(card_w, card_h) * 0.18)
    ImageDraw.Draw(card).rounded_rectangle(
        (0, 0, card_w - 1, card_h - 1), radius=radius, fill=(255, 255, 255, 235)
    )
    card.alpha_composite(logo, (pad, pad))
    canvas.alpha_composite(card, (cx - card_w // 2, cy - card_h // 2))


def build_collage(photos: list[bytes], *, size: int = CANVAS) -> bytes:
    """Return PNG bytes: up to 4 photos laid out with the logo centered.

    Raises CollageError when no usable photo is supplied.
    """
    loaded = [img for p in photos[:4] if (img := _load(p)) is not None]
    if not loaded:
        raise CollageError("no usable photos to build a collage")

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (*BRAND_BG, 255))
    rects = _tile_rects(len(loaded))
    for img, (left, top, right, bottom) in zip(loaded, rects, strict=False):
        w, h = right - left, bottom - top
        tile = ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=(0.5, 0.5))
        canvas.paste(tile, (left, top))

    _logo_overlay(canvas)

    if size != CANVAS:
        canvas = canvas.resize((size, size), Image.LANCZOS)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
