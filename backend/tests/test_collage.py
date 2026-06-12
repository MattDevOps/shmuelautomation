"""Tests for the pure collage builder."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from shmuel_backend.collage import CANVAS, CollageError, build_collage


def _photo(color: tuple[int, int, int], size: tuple[int, int] = (640, 480)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


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
