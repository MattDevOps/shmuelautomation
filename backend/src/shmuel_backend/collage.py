"""Build share-ready branded images for a property.

Two products, one look:

- `build_collage` lays up to four property photos into a square canvas (a
  single image, a 1x2 split, or a 2x2 grid), sized for WhatsApp (1080x1080
  by default).
- `watermark_photo` brands a single photo at (capped) full size.

Both overlay the Classic Jerusalem logo centered on a soft rounded card so it
stays legible over any photo.

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

# Logo sizing/backing, as fractions of the image's shorter edge.
_LOGO_WIDTH_FRAC = 0.30
_CARD_PAD_FRAC = 0.035
WATERMARK_MAX_EDGE = 1600
_JPEG_QUALITY = 88


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


def load_image(photo: bytes) -> Image.Image | None:
    """Decode `photo` to an RGB image, or None for a corrupt/non-image blob."""
    try:
        img = Image.open(io.BytesIO(photo))
        img.load()
        return img.convert("RGB")
    except Exception:
        # A corrupt / non-image blob shouldn't sink the whole collage.
        return None


def _logo_overlay(canvas: Image.Image) -> None:
    """Center the logo card on `canvas`, scaled to its shorter edge."""
    if not LOGO_PATH.exists():
        return
    base = min(canvas.size)
    logo = Image.open(LOGO_PATH).convert("RGBA")
    target_w = int(base * _LOGO_WIDTH_FRAC)
    if target_w < 1 or int(logo.height * target_w / logo.width) < 1:
        return  # canvas too tiny for a legible logo; skip rather than crash
    scale = target_w / logo.width
    logo = logo.resize((target_w, int(logo.height * scale)), Image.LANCZOS)

    pad = int(base * _CARD_PAD_FRAC)
    card_w, card_h = logo.width + pad * 2, logo.height + pad * 2
    cx, cy = canvas.width // 2, canvas.height // 2

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
    loaded = [img for p in photos[:4] if (img := load_image(p)) is not None]
    return build_collage_from_images(loaded, size=size)


def build_collage_from_images(
    images: list[Image.Image], *, size: int = CANVAS
) -> bytes:
    """build_collage for already-decoded images, so a caller that decoded
    them for hashing doesn't pay a second decode. Raises CollageError when
    no image is supplied.
    """
    loaded = images[:4]
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


def watermark_photo(photo: bytes, *, max_edge: int = WATERMARK_MAX_EDGE) -> bytes:
    """Return JPEG bytes: the photo with the logo card centered on it.

    The photo is downscaled so its long edge is at most `max_edge` (never
    upscaled) and branded with the same rounded-card logo the collage uses,
    scaled to the image's shorter edge. Raises CollageError on unusable input.
    """
    img = load_image(photo)
    if img is None:
        raise CollageError("unusable photo bytes")
    return watermark_image(img, max_edge=max_edge)


def watermark_image(image: Image.Image, *, max_edge: int = WATERMARK_MAX_EDGE) -> bytes:
    """watermark_photo for an already-decoded image."""
    img = image
    if max(img.size) > max_edge:
        scale = max_edge / max(img.size)
        img = img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
            Image.LANCZOS,
        )

    canvas = img.convert("RGBA")
    _logo_overlay(canvas)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()
