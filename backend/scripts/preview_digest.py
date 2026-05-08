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
from shmuel_backend.models import NewsletterSubscriber, Property  # noqa: E402
from shmuel_backend.newsletter_compose import render_digest  # noqa: E402


def _prop(
    *,
    type_: PropertyType,
    neighborhood: str,
    price: Decimal,
    rooms: float,
    size: int,
) -> Property:
    return Property(
        id=uuid.uuid4(),
        type=type_,
        status=PropertyStatus.AVAILABLE,
        price=price,
        currency="NIS",
        rooms=rooms,
        size_sqm=size,
        neighborhood=neighborhood,
        city="Jerusalem",
        created_at=datetime.utcnow(),
    )


sub = NewsletterSubscriber(
    id=uuid.uuid4(),
    email="preview@example.com",
    language="en",
    confirmation_token="confirm-token",
    unsubscribe_token="unsub-token",
    confirmed_at=datetime.utcnow(),
    created_at=datetime.utcnow(),
)

properties = [
    _prop(type_=PropertyType.RENT, neighborhood="Rehavia", price=Decimal("9500"), rooms=4, size=95),
    _prop(type_=PropertyType.SALE, neighborhood="Baka", price=Decimal("3200000"), rooms=3, size=78),
    _prop(
        type_=PropertyType.RENT, neighborhood="Nachlaot", price=Decimal("7200"), rooms=2, size=55
    ),
]

rendered = render_digest(sub, properties, photos_by_property={})
out = Path("/tmp/digest-preview.html")
out.write_text(rendered.html)
print(f"wrote {out}")
print(f"subject: {rendered.subject}")
