"""End-to-end auto-post demo — 'as if a 2nd number were paired'.

Drives the REAL auto_poster.dispatch_slot against the local dev DB and a
mock daemon (scripts/mock_daemon.py). Exercises the real audience
routing, the real Hebrew caption (compose_post), and the real collage
builder (collage.build_collage with the real Classic Jerusalem logo).
The only thing faked is the WhatsApp connection itself (the mock) and the
photo source (generated room images, since Drive isn't wired locally).

Run the mock daemon first, then:  uv run python scripts/run_autopost_demo.py
"""
from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime

from PIL import Image, ImageDraw
from sqlalchemy import select

from shmuel_backend.collage import build_collage
from shmuel_backend.config import settings
from shmuel_backend.db import SessionLocal
from shmuel_backend.enums import PostSlotStatus, PropertyStatus, PropertyType
from shmuel_backend.models import PostSlot, Property

DAEMON_URL = "http://127.0.0.1:8799"
DAEMON_TOKEN = "mock-daemon-token"


def _room_photo(label: str, color: tuple[int, int, int]) -> bytes:
    """A stand-in 'property photo' so the collage looks like a real listing."""
    img = Image.new("RGB", (1024, 768), color)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 620, 1024, 768], fill=(0, 0, 0))
    d.text((40, 660), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def _fake_collage(_session, _pid) -> bytes:
    """Real collage builder, fed generated room photos + the real logo."""
    photos = [
        _room_photo("Living room", (172, 142, 104)),
        _room_photo("Kitchen", (120, 134, 150)),
        _room_photo("Bedroom", (150, 120, 120)),
        _room_photo("View", (110, 150, 130)),
    ]
    return build_collage(photos)


async def _dispatch_for(session, prop: Property) -> None:
    from shmuel_backend import auto_poster

    slot = PostSlot(
        property_id=prop.id,
        scheduled_for=datetime.now(UTC).replace(tzinfo=None),
        status=PostSlotStatus.PENDING,
    )
    session.add(slot)
    await session.flush()
    await session.refresh(slot, attribute_names=["property"])

    label = f"{prop.type.value} / {prop.neighborhood or prop.city} / {prop.price:,} {prop.currency}"
    print(f"\n=== Dispatching: {label}  (slot {str(slot.id)[:8]}) ===")
    result = await auto_poster.dispatch_slot(session, slot)
    print(f"    attempted={result.attempted}  succeeded={result.succeeded}  "
          f"skipped={result.skipped_reason}  failures={result.group_failures}")
    print(f"    slot status after: {slot.status.value}"
          + (f"  posted_at={slot.posted_at}" if slot.posted_at else ""))

    # Clean up the demo slot so we don't pollute the dev queue.
    await session.delete(slot)
    await session.commit()


async def main() -> None:
    # Point the backend at the mock daemon (same trick the unit tests use).
    settings.whatsapp_daemon_url = DAEMON_URL
    settings.whatsapp_daemon_token = DAEMON_TOKEN

    # Run the real collage builder instead of the Drive-backed one.
    from shmuel_backend import auto_poster
    auto_poster.render_property_collage = _fake_collage

    async with SessionLocal() as session:
        rent = (await session.execute(
            select(Property).where(
                Property.type == PropertyType.RENT,
                Property.status == PropertyStatus.AVAILABLE,
            ).limit(1)
        )).scalar_one_or_none()
        sale = (await session.execute(
            select(Property).where(
                Property.type == PropertyType.SALE,
                Property.status == PropertyStatus.AVAILABLE,
            ).limit(1)
        )).scalar_one_or_none()

        if rent is None and sale is None:
            print("No AVAILABLE properties in dev.sqlite — nothing to demo.")
            return
        for prop in (rent, sale):
            if prop is not None:
                await _dispatch_for(session, prop)

    print("\nDone. Check the mock daemon's output dir for the captured "
          "collage PNG(s) + caption text — that is exactly what the paired "
          "number would post to each matching WhatsApp group.")


if __name__ == "__main__":
    asyncio.run(main())
