from decimal import Decimal

from shmuel_backend.compose import (
    compose_post,
    facebook_share_url,
    whatsapp_share_url,
)
from shmuel_backend.enums import (
    BrokerFeeStatus,
    PropertyStatus,
    PropertyType,
)
from shmuel_backend.models import CloudPhoto, Property


def _prop(**overrides: object) -> Property:
    p = Property()
    p.type = PropertyType.RENT  # type: ignore[assignment]
    p.status = PropertyStatus.AVAILABLE  # type: ignore[assignment]
    p.price = Decimal("8500")  # type: ignore[assignment]
    p.currency = "ILS"  # type: ignore[assignment]
    p.rooms = Decimal("3.5")  # type: ignore[assignment]
    p.size_sqm = 80  # type: ignore[assignment]
    p.floor = 2  # type: ignore[assignment]
    p.address = "12 Emek Refaim"  # type: ignore[assignment]
    p.neighborhood = "Baka"  # type: ignore[assignment]
    p.city = "Jerusalem"  # type: ignore[assignment]
    p.broker_fee_status = BrokerFeeStatus.YES  # type: ignore[assignment]
    p.description = "Bright top-floor apartment"  # type: ignore[assignment]
    p.yad2_url = None  # type: ignore[assignment]
    p.broker_fee_amount = None  # type: ignore[assignment]
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def test_english_rental_includes_facts_and_price() -> None:
    text = compose_post(_prop(), lang="en")
    assert "For rent" in text
    assert "Baka" in text
    assert "3 rooms" in text or "3.5 rooms" in text  # exact form
    assert "ILS 8,500" in text
    assert "12 Emek Refaim" in text
    assert "Bright top-floor apartment" in text


def test_hebrew_rental_uses_hebrew_labels() -> None:
    text = compose_post(_prop(), lang="he")
    assert "להשכרה" in text
    assert "בBaka" in text or "ב Baka" in text  # neighborhood preposition
    assert "ILS 8,500" in text
    assert "מ\"ר" in text


def test_sale_uses_for_sale_label() -> None:
    text = compose_post(
        _prop(type=PropertyType.SALE, price=Decimal("3200000")), lang="en"
    )
    assert "For sale" in text
    assert "ILS 3,200,000" in text


def test_compose_with_no_optional_fields() -> None:
    text = compose_post(
        _prop(
            rooms=None,
            size_sqm=None,
            floor=None,
            address=None,
            neighborhood=None,
            description=None,
        ),
        lang="en",
    )
    assert "For rent" in text
    assert "ILS 8,500" in text
    # No empty bullet line, no extra blank lines
    assert "·  ·" not in text


def test_compose_appends_first_photo_url() -> None:
    photo = CloudPhoto()
    photo.web_view_url = "https://www.dropbox.com/file/abc"  # type: ignore[assignment]
    photo.thumbnail_url = "https://thumb"  # type: ignore[assignment]
    photo.file_name = "front.jpg"  # type: ignore[assignment]
    text = compose_post(_prop(), lang="en", photos=[photo])
    assert "https://www.dropbox.com/file/abc" in text


def test_compose_appends_yad2_link_when_no_photos() -> None:
    text = compose_post(
        _prop(yad2_url="https://www.yad2.co.il/realestate/abc"),
        lang="en",
    )
    assert "https://www.yad2.co.il/realestate/abc" in text


def test_whatsapp_share_url_encodes_text() -> None:
    url = whatsapp_share_url("Hello, world!")
    assert url.startswith("https://wa.me/?text=")
    assert "Hello%2C%20world" in url


def test_whatsapp_share_url_with_phone_strips_non_digits() -> None:
    url = whatsapp_share_url("hi", phone="+972 50-000-0000")
    assert url.startswith("https://wa.me/972500000000?text=")


def test_facebook_share_url_encodes() -> None:
    url = facebook_share_url("https://classicjerusalem.com/p/abc")
    assert url.startswith("https://www.facebook.com/sharer/sharer.php?u=")
    assert "classicjerusalem.com" in url
