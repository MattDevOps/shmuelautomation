"""Render a digest email to /tmp/digest-preview.html for visual review."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("RESEND_API_KEY", "preview")
os.environ.setdefault("ADMIN_API_KEY", "preview")

from shmuel_backend.enums import PropertyStatus, PropertyType  # noqa: E402
from shmuel_backend.models import CloudPhoto, NewsletterSubscriber, Property  # noqa: E402
from shmuel_backend.newsletter_compose import render_digest  # noqa: E402


def _prop(
    *,
    type_: PropertyType,
    neighborhood: str,
    price: Decimal,
    rooms: float,
    size: int,
    address: str = "",
    floor: int | None = None,
    description: str = "",
) -> Property:
    return Property(
        id=uuid.uuid4(),
        type=type_,
        status=PropertyStatus.AVAILABLE,
        price=price,
        currency="NIS",
        rooms=rooms,
        size_sqm=size,
        floor=floor,
        address=address,
        neighborhood=neighborhood,
        city="Jerusalem",
        description=description,
        created_at=datetime.utcnow(),
    )


_LANG = os.environ.get("LANG_OVERRIDE", "en")

sub = NewsletterSubscriber(
    id=uuid.uuid4(),
    email="preview@example.com",
    language=_LANG,
    confirmation_token="confirm-token",
    unsubscribe_token="unsub-token",
    confirmed_at=datetime.utcnow(),
    created_at=datetime.utcnow(),
)

properties = [
    _prop(
        type_=PropertyType.RENT,
        neighborhood="Rehavia",
        address="Sderot Ben Maimon",
        price=Decimal("9500"),
        rooms=4,
        size=95,
        floor=3,
        description=(
            "Bright and spacious 4-room apartment on a quiet tree-lined street, "
            "fully furnished, with a sunny balcony overlooking the neighborhood. "
            "Two bathrooms, large kitchen, central heating, Shabbat elevator, parking included."
        ),
    ),
    _prop(
        type_=PropertyType.SALE,
        neighborhood="Baka",
        address="Yehuda HaNasi",
        price=Decimal("3200000"),
        rooms=3,
        size=78,
        floor=2,
        description=(
            "Charming Jerusalem-stone garden apartment in the heart of Baka. "
            "Renovated kitchen and bathrooms, original tile floors, private "
            "30 sqm garden with mature olive trees. Walking distance to Emek Refaim."
        ),
    ),
    _prop(
        type_=PropertyType.RENT,
        neighborhood="Nachlaot",
        address="Mevoh Beit David",
        price=Decimal("7200"),
        rooms=2,
        size=55,
        description=(
            "Cozy artist-style 2-room flat in the alleys of Nachlaot. "
            "Stone walls, vaulted ceilings, fully furnished. Steps from Mahane Yehuda market."
        ),
    ),
]

# Seed lead photos so the preview reflects production: each property's
# first CloudPhoto.thumbnail_url is what appears in the digest card.
# These are stand-in Unsplash images sized for an email column.
_STUB_PHOTOS = [
    "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=720&q=80",
    "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=720&q=80",
    "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=720&q=80",
]
photos_by_property = {
    p.id: [
        CloudPhoto(
            id=uuid.uuid4(),
            property_id=p.id,
            provider="drive",
            external_id=f"stub-{i}",
            folder_external_id="stub-folder",
            file_name=f"lead-{i}.jpg",
            mime_type="image/jpeg",
            size_bytes=1,
            checksum=f"stub-{i}",
            thumbnail_url=url,
            web_view_url=url,
            created_at=datetime.utcnow(),
        )
    ]
    for i, (p, url) in enumerate(zip(properties, _STUB_PHOTOS, strict=False))
}

rendered = render_digest(sub, properties, photos_by_property=photos_by_property)
out = Path("/tmp/digest-preview.html")
out.write_text(rendered.html)
print(f"wrote {out}")
print(f"subject: {rendered.subject}")
