from decimal import Decimal

from shmuel_backend.enums import PropertyType
from shmuel_backend.wp_import import (
    build_planned,
    classify_type,
    find_imported_wp_ids,
    import_marker,
    is_available,
    normalize_gallery,
)


def _row(**details: object) -> dict:
    """A minimal WP property row with overridable details_properties fields."""
    base = {
        "code_property": "117",
        "property_name": "LUXURY APARTMENT",
        "price_shekels": "35860",
        "neighborhood": "Talbye",
        "neighborhood_selector": "Talbiya",
        "street_name": "Disraeli",
        "ribbon_cintillo": "For Rent - Long Term",
        "beds": "4",
        "baths": "3.4",
        "sqm": "200",
        "rented_day": "",
    }
    base.update(details)
    return {
        "id": 2786,
        "slug": "p-117-for-rent-disraeli",
        "link": "https://realestateadmin2025.classicjerusalem.com/properties/p-117/",
        "categories": [10],
        "acf": {
            "details_properties": base,
            "description": {
                "paragraph_1": "First paragraph &amp; details.",
                "paragraph_2": "Second paragraph.",
            },
        },
    }


def test_classify_rent_sale_and_dual() -> None:
    assert classify_type(_row()) == (PropertyType.RENT, False)

    sale = _row(ribbon_cintillo="For Sale")
    sale["categories"] = [3]
    assert classify_type(sale) == (PropertyType.SALE, False)

    dual = _row(ribbon_cintillo="For Rent - Long Term Term | For Sale")
    dual["categories"] = [3, 10]
    ptype, is_dual = classify_type(dual)
    assert ptype == PropertyType.RENT  # rent is the primary for dual listings
    assert is_dual is True


def test_classify_featured_only_falls_back_to_ribbon() -> None:
    featured = _row(ribbon_cintillo="For Sale")
    featured["categories"] = [13]  # featured-properties only
    assert classify_type(featured)[0] == PropertyType.SALE


def test_availability_filters() -> None:
    assert is_available(_row()) is True
    assert is_available(_row(rented_day="2025-01-01")) is False

    hidden = _row()
    hidden["categories"] = [10, 14]  # hide bucket
    assert is_available(hidden) is False

    uncategorized = _row()
    uncategorized["categories"] = [1]
    assert is_available(uncategorized) is False


def test_build_planned_maps_core_fields() -> None:
    p = build_planned(_row())
    assert p is not None
    k = p.kwargs
    assert k["type"] == PropertyType.RENT
    assert k["price"] == Decimal("35860")
    assert k["currency"] == "ILS"
    assert k["rooms"] == Decimal("4.0")
    assert k["size_sqm"] == 200
    assert k["neighborhood"] == "Talbiya"  # selector wins over misspelled field
    assert k["address"] == "Disraeli"
    assert k["city"] == "Jerusalem"
    # description joins headline + paragraphs and unescapes entities
    assert "LUXURY APARTMENT" in str(k["description"])
    assert "First paragraph & details." in str(k["description"])
    # notes carry the idempotency marker + provenance
    assert import_marker(2786) in str(k["notes"])
    assert "WP code: 117" in str(k["notes"])
    assert "Beds: 4" in str(k["notes"])


def test_build_planned_skips_when_unavailable_or_priceless() -> None:
    assert build_planned(_row(rented_day="2025-01-01")) is None
    assert build_planned(_row(price_shekels="")) is None
    assert build_planned(_row(price_shekels="0")) is None


def test_dual_listing_notes_mention_other_intent() -> None:
    dual = _row(ribbon_cintillo="For Rent - Long Term Term | For Sale")
    dual["categories"] = [3, 10]
    p = build_planned(dual)
    assert p is not None
    assert "also listed for sale" in str(p.kwargs["notes"]).lower()


def test_normalize_gallery_dict_and_list_and_best_url() -> None:
    dict_form = _row()
    dict_form["acf"]["photo_gallery"] = {
        "photo_gallery": {
            "0": {"full_image_url": "https://x/a.jpeg", "title": "a"},
            "1": {
                "full_image_url": "",
                "media_details": {
                    "sizes": {"large": {"source_url": "https://x/b-large.jpeg"}}
                },
            },
        }
    }
    items = normalize_gallery(dict_form)
    assert len(items) == 2

    p = build_planned(dict_form)
    assert p is not None
    assert [ph.url for ph in p.photos] == [
        "https://x/a.jpeg",
        "https://x/b-large.jpeg",  # falls back to media_details when full is empty
    ]
    assert p.photos[0].file_name == "a.jpeg"


def test_max_photos_cap() -> None:
    row = _row()
    row["acf"]["photo_gallery"] = {
        "photo_gallery": [
            {"full_image_url": f"https://x/{i}.jpeg"} for i in range(10)
        ]
    }
    p = build_planned(row, max_photos=3)
    assert p is not None
    assert len(p.photos) == 3


def test_find_imported_wp_ids() -> None:
    notes = [
        f"{import_marker(11)}\nWP code: 11",
        None,
        f"some text {import_marker(22)} more",
        "no marker here",
    ]
    assert find_imported_wp_ids(notes) == {11, 22}
