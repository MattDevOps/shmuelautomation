"""Tests for the pure collage/watermark builders and photo diversity picks."""
from __future__ import annotations

import io
import random

import pytest
from PIL import Image, ImageDraw

from shmuel_backend.collage import CANVAS, CollageError, build_collage, watermark_photo
from shmuel_backend.photo_select import (
    NEAR_DUPLICATE_BITS,
    dhash,
    hamming,
    select_diverse,
)


def _photo(color: tuple[int, int, int], size: tuple[int, int] = (640, 480)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _ramp(size: tuple[int, int] = (320, 240), *, reverse: bool = False) -> Image.Image:
    """Horizontal brightness ramp; reversed, its dHash flips every bit."""
    img = Image.new("L", size)
    d = ImageDraw.Draw(img)
    for x in range(size[0]):
        v = int(255 * x / size[0])
        d.line([(x, 0), (x, size[1])], fill=255 - v if reverse else v)
    return img.convert("RGB")


def _noise(seed: int, size: tuple[int, int] = (90, 80)) -> Image.Image:
    """Deterministic per-seed noise; distinct seeds hash far apart."""
    rng = random.Random(seed)
    data = bytes(rng.randrange(256) for _ in range(size[0] * size[1]))
    return Image.frombytes("L", size, data).convert("RGB")


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_build_collage_is_square_png(n: int) -> None:
    photos = [_photo((40 * i, 80, 120)) for i in range(n)]
    png = build_collage(photos)
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (CANVAS, CANVAS)


def test_more_than_four_photos_uses_first_four() -> None:
    photos = [_photo((10, 20, 30)) for _ in range(7)]
    png = build_collage(photos)
    assert Image.open(io.BytesIO(png)).size == (CANVAS, CANVAS)


def test_custom_size() -> None:
    png = build_collage([_photo((200, 100, 50))], size=512)
    assert Image.open(io.BytesIO(png)).size == (512, 512)


def test_corrupt_blob_is_skipped_not_fatal() -> None:
    png = build_collage([b"not-an-image", _photo((90, 160, 110))])
    assert Image.open(io.BytesIO(png)).size == (CANVAS, CANVAS)


def test_no_usable_photos_raises() -> None:
    with pytest.raises(CollageError):
        build_collage([b"garbage", b""])

    with pytest.raises(CollageError):
        build_collage([])


# ── dHash + diversity selection ──


def test_dhash_identical_images_hash_identically() -> None:
    assert dhash(_noise(1)) == dhash(_noise(1))


def test_dhash_very_different_images_hash_far_apart() -> None:
    # Mirrored ramps flip every difference bit: the maximal distance.
    assert hamming(dhash(_ramp()), dhash(_ramp(reverse=True))) == 64
    assert hamming(dhash(_noise(1)), dhash(_noise(2))) > 20


def test_dhash_survives_reencode_and_brightness_shift() -> None:
    """True near-duplicates must land within the dedup threshold."""
    img = _noise(1)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    reencoded = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    brighter = img.point(lambda p: min(255, p + 12))
    assert hamming(dhash(img), dhash(reencoded)) <= NEAR_DUPLICATE_BITS
    assert hamming(dhash(img), dhash(brighter)) <= NEAR_DUPLICATE_BITS


def test_select_diverse_anchors_lead_and_skips_near_duplicate() -> None:
    lead = _noise(1)
    near_dup = lead.point(lambda p: min(255, p + 12))  # same shot, brighter
    picked = select_diverse([lead, near_dup, _noise(2), _noise(3)], 3)
    assert picked[0] == 0  # lead photo always anchors
    assert 1 not in picked  # the near-duplicate never makes it in
    assert sorted(picked) == [0, 2, 3]


def test_select_diverse_returns_fewer_when_all_else_duplicates() -> None:
    lead = _noise(1)
    dup = lead.point(lambda p: min(255, p + 12))
    assert select_diverse([lead, dup], 4) == [0]
    assert select_diverse([], 4) == []


# ── watermark_photo ──


def test_watermark_photo_returns_jpeg_same_size_when_small() -> None:
    jpeg = watermark_photo(_photo((90, 160, 110), size=(800, 600)))
    img = Image.open(io.BytesIO(jpeg))
    assert img.format == "JPEG"
    assert img.size == (800, 600)  # under max_edge, never upscaled
    # The logo card sits centered, so the middle no longer matches the photo
    # while an untouched corner still does (within JPEG wobble).
    r, g, b = img.getpixel((400, 300))
    assert abs(r - 90) + abs(g - 160) + abs(b - 110) > 60
    r, g, b = img.getpixel((10, 10))
    assert abs(r - 90) + abs(g - 160) + abs(b - 110) < 30


def test_watermark_photo_caps_long_edge() -> None:
    jpeg = watermark_photo(_photo((90, 160, 110), size=(3200, 2400)), max_edge=1600)
    assert Image.open(io.BytesIO(jpeg)).size == (1600, 1200)


def test_watermark_photo_raises_on_garbage() -> None:
    with pytest.raises(CollageError):
        watermark_photo(b"not-an-image")


def test_watermark_photo_survives_tiny_image() -> None:
    """A decodable but tiny image must not crash the logo overlay: the logo
    is skipped when it can't render at 1px or more. Regression for a bare
    ValueError that used to escape Image.resize on a sub-4px shorter edge."""
    jpeg = watermark_photo(_photo((90, 160, 110), size=(2, 2)))
    img = Image.open(io.BytesIO(jpeg))
    assert img.format == "JPEG"
    assert img.size == (2, 2)
