"""Tests for the share-pack service (collage_service.render_share_pack & co).

Drive is stubbed at the storage layer so these exercise the real pipeline:
one parallel download pass, dHash dedup with collage backfill, the pack
cache, and the branded renders.
"""
from __future__ import annotations

import io
import random
import uuid
from decimal import Decimal

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import collage_service
from shmuel_backend.cloud.crypto import encrypt
from shmuel_backend.cloud.storage import CloudStorageError
from shmuel_backend.collage import CANVAS, watermark_photo
from shmuel_backend.collage_service import (
    render_branded_photo,
    render_property_collage,
    render_share_pack,
)
from shmuel_backend.enums import BrokerFeeStatus, PropertyStatus, PropertyType
from shmuel_backend.models import CloudConnection, CloudPhoto, Property


@pytest.fixture(autouse=True)
def _clear_pack_cache() -> None:
    collage_service._pack_cache.clear()


def _noise_jpeg(seed: int, size: tuple[int, int] = (400, 300)) -> bytes:
    rng = random.Random(seed)
    data = bytes(rng.randrange(256) for _ in range(size[0] * size[1]))
    img = Image.frombytes("L", size, data).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _solid_jpeg(color: tuple[int, int, int], size: tuple[int, int] = (400, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _reencoded(jpeg: bytes) -> bytes:
    """The same shot re-exported at a lower quality: a classic near-duplicate."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


async def _make_property(session: AsyncSession) -> Property:
    prop = Property(
        type=PropertyType.RENT,
        status=PropertyStatus.AVAILABLE,
        price=Decimal("8000"),
        currency="ILS",
        neighborhood="Talbiya",
        broker_fee_status=BrokerFeeStatus.YES,
    )
    session.add(prop)
    await session.flush()
    return prop


async def _connect_drive(session: AsyncSession) -> None:
    session.add(
        CloudConnection(
            provider="google_drive",
            account_email="shmuel@example.com",
            encrypted_refresh_token=encrypt("rt-1"),
        )
    )
    await session.flush()


def _add_photo(session: AsyncSession, prop: Property, name: str) -> CloudPhoto:
    photo = CloudPhoto(
        property_id=prop.id,
        provider="google_drive",
        external_id=f"drive-{name}",
        folder_external_id="folder-1",
        file_name=name,
        mime_type="image/jpeg",
        size_bytes=1234,
        checksum=f"sum-{name}",
    )
    session.add(photo)
    return photo


def _stub_downloads(
    monkeypatch: pytest.MonkeyPatch, blobs: dict[str, bytes]
) -> list[str]:
    """Route Drive downloads to `blobs` by external id; missing ids raise
    CloudStorageError. Skips the real token refresh. Returns the list of
    requested ids (appended in request order)."""
    requested: list[str] = []

    async def fake_refresh(_refresh_token: str) -> str:
        return "access-1"

    async def fake_download(_access: str, external_id: str) -> bytes:
        requested.append(external_id)
        if external_id not in blobs:
            raise CloudStorageError(f"no such file: {external_id}")
        return blobs[external_id]

    monkeypatch.setattr(collage_service, "refresh_access_token", fake_refresh)
    monkeypatch.setattr(
        collage_service._storage, "download_file_with_access", fake_download
    )
    # The single-photo path goes through download_file(refresh_token, id).
    monkeypatch.setattr(
        collage_service._storage,
        "download_file",
        lambda _tok, ext_id: fake_download("access-1", ext_id),
    )
    return requested


@pytest.mark.asyncio
async def test_share_pack_dedupes_and_brands(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    prop = await _make_property(session)
    await _connect_drive(session)
    lead = _noise_jpeg(1)
    photos = {
        "drive-a.jpg": lead,
        "drive-b.jpg": _reencoded(lead),  # near-dup of the lead; must drop
        "drive-c.jpg": _noise_jpeg(2),
        "drive-d.jpg": _noise_jpeg(3),
        "drive-e.jpg": _noise_jpeg(4),
    }
    for name in photos:
        _add_photo(session, prop, name.removeprefix("drive-"))
    await session.commit()
    _stub_downloads(monkeypatch, photos)

    pack = await render_share_pack(session, prop.id)
    assert pack is not None

    collage = Image.open(io.BytesIO(pack.collage_png))
    assert collage.format == "PNG"
    assert collage.size == (CANVAS, CANVAS)

    # 5 candidates, 1 near-duplicate: 4 branded photos, lead first (the
    # branded lead is byte-identical to watermarking the lead directly).
    assert len(pack.photos) == 4
    assert pack.photos[0] == watermark_photo(lead)
    assert all(
        Image.open(io.BytesIO(jpeg)).format == "JPEG" for jpeg in pack.photos
    )


@pytest.mark.asyncio
async def test_share_pack_backfills_collage_when_dedup_overfires(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Four visually distinct but dHash-identical photos (flat walls all hash
    to 0) must still yield a 4-tile collage via gallery-order backfill, even
    though the branded set stays deduped."""
    prop = await _make_property(session)
    await _connect_drive(session)
    colors = [(200, 40, 40), (40, 160, 40), (40, 60, 200), (220, 200, 40)]
    photos = {
        f"drive-{i}.jpg": _solid_jpeg(color) for i, color in enumerate(colors)
    }
    for name in photos:
        _add_photo(session, prop, name.removeprefix("drive-"))
    await session.commit()
    _stub_downloads(monkeypatch, photos)

    pack = await render_share_pack(session, prop.id)
    assert pack is not None
    assert len(pack.photos) == 1  # dedup: every wall "matches" the lead

    # One sample point per 2x2 quadrant, away from the center logo card.
    collage = Image.open(io.BytesIO(pack.collage_png))
    samples = [
        collage.getpixel((200, 200)),
        collage.getpixel((880, 200)),
        collage.getpixel((200, 880)),
        collage.getpixel((880, 880)),
    ]
    for expected, got in zip(colors, samples, strict=True):
        assert sum(abs(e - g) for e, g in zip(expected, got, strict=True)) < 40


@pytest.mark.asyncio
async def test_share_pack_is_cached_per_photo_set(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    prop = await _make_property(session)
    await _connect_drive(session)
    _add_photo(session, prop, "a.jpg")
    _add_photo(session, prop, "b.jpg")
    await session.commit()
    requested = _stub_downloads(
        monkeypatch, {"drive-a.jpg": _noise_jpeg(1), "drive-b.jpg": _noise_jpeg(2)}
    )

    first = await render_share_pack(session, prop.id)
    assert first is not None
    downloads_after_first = len(requested)
    assert downloads_after_first == 2

    # Second render (any caller) reuses the cached pack: no new downloads.
    second = await render_share_pack(session, prop.id)
    assert second is not None
    assert second.collage_png == first.collage_png
    assert len(requested) == downloads_after_first

    # A new photo changes the cache key, forcing a fresh render.
    _add_photo(session, prop, "c.jpg")
    await session.commit()
    await render_share_pack(session, prop.id)
    assert len(requested) > downloads_after_first


@pytest.mark.asyncio
async def test_share_pack_caps_individual_photos(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    prop = await _make_property(session)
    await _connect_drive(session)
    photos = {f"drive-{i}.jpg": _noise_jpeg(i) for i in range(1, 6)}
    for name in photos:
        _add_photo(session, prop, name.removeprefix("drive-"))
    await session.commit()
    _stub_downloads(monkeypatch, photos)

    pack = await render_share_pack(session, prop.id, max_photos=2)
    assert pack is not None
    assert len(pack.photos) == 2

    # include_branded=False still returns the collage but no photo payloads.
    collage_only = await render_share_pack(session, prop.id, include_branded=False)
    assert collage_only is not None
    assert collage_only.photos == []
    assert collage_only.collage_png == pack.collage_png


@pytest.mark.asyncio
async def test_share_pack_none_paths(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    prop = await _make_property(session)
    # No Drive connection at all.
    assert await render_share_pack(session, prop.id) is None

    # Connected but no photos.
    await _connect_drive(session)
    await session.commit()
    assert await render_share_pack(session, prop.id) is None

    # Photos exist but every download fails.
    _add_photo(session, prop, "gone.jpg")
    await session.commit()
    _stub_downloads(monkeypatch, {})
    assert await render_share_pack(session, prop.id) is None


@pytest.mark.asyncio
async def test_render_property_collage_still_works(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    prop = await _make_property(session)
    await _connect_drive(session)
    _add_photo(session, prop, "a.jpg")
    await session.commit()
    _stub_downloads(monkeypatch, {"drive-a.jpg": _noise_jpeg(1)})

    png = await render_property_collage(session, prop.id)
    assert png is not None
    assert Image.open(io.BytesIO(png)).size == (CANVAS, CANVAS)


@pytest.mark.asyncio
async def test_render_branded_photo_downloads_only_that_file(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    prop = await _make_property(session)
    await _connect_drive(session)
    target = _add_photo(session, prop, "a.jpg")
    _add_photo(session, prop, "b.jpg")
    await session.commit()
    requested = _stub_downloads(
        monkeypatch, {"drive-a.jpg": _noise_jpeg(1), "drive-b.jpg": _noise_jpeg(2)}
    )

    jpeg = await render_branded_photo(session, prop.id, target.id)
    assert jpeg is not None
    assert Image.open(io.BytesIO(jpeg)).format == "JPEG"
    assert requested == ["drive-a.jpg"]  # one download, not the whole gallery

    # Unknown photo id / wrong property: None.
    assert await render_branded_photo(session, prop.id, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_render_branded_photo_garbage_bytes_yield_none(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unusable stored bytes must read as 'no photo', never an exception."""
    prop = await _make_property(session)
    await _connect_drive(session)
    target = _add_photo(session, prop, "bad.jpg")
    await session.commit()
    _stub_downloads(monkeypatch, {"drive-bad.jpg": b"not-an-image"})

    assert await render_branded_photo(session, prop.id, target.id) is None