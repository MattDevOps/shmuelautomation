"""Canonical property amenity vocabulary + Yad2 mapping.

A property's amenities are stored as a JSON list of these slugs on
`Property.amenities` (mirroring how `Contact.segments` works). Keeping the
vocabulary in one place lets the Yad2 parser, the API schema validator, and
the admin form all agree on the same slug set and ordering.

The Yad2 listing payload exposes these as booleans under the ad's
`inProperty` object (e.g. `includeSecurityRoom` is the mamad / safe room),
plus a couple of counts under `additionalDetails` (parking spaces, balconies).
"""

# slug -> English label shown in the admin. Order here is the canonical order
# amenities are stored and rendered in. Safe room (mamad) leads because it's
# the field most often asked about on Jerusalem listings.
AMENITY_LABELS: dict[str, str] = {
    "security_room": "Safe room (mamad)",
    "parking": "Parking",
    "elevator": "Elevator",
    "balcony": "Balcony",
    "air_conditioning": "Air conditioning",
    "storage": "Storage room",
    "bars": "Window bars",
    "accessible": "Accessible",
    "renovated": "Renovated",
    "furnished": "Furnished",
    "solar_boiler": "Solar water heater",
    "shelter": "Building shelter",
}

AMENITY_SLUGS: tuple[str, ...] = tuple(AMENITY_LABELS)

# Yad2 `inProperty` boolean key -> our slug. Values are `true` when the ad
# claims the feature (mamad was seen as both true and false across listings).
_YAD2_INPROPERTY: dict[str, str] = {
    "includeSecurityRoom": "security_room",
    "includeParking": "parking",
    "includeElevator": "elevator",
    "includeBalcony": "balcony",
    "includeAirconditioner": "air_conditioning",
    "includeWarehouse": "storage",
    "includeBars": "bars",
    "isHandicapped": "accessible",
    "isRenovated": "renovated",
    "includeFurniture": "furnished",
    "includeBoiler": "solar_boiler",
    "includeBuildingShelter": "shelter",
}


def _positive_count(value: object) -> bool:
    # bool is an int subclass — exclude it so a stray JSON true isn't a count.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def normalize_amenities(values: object) -> list[str]:
    """Keep only known slugs, drop dupes, return them in canonical order."""
    if not isinstance(values, (list, tuple, set)):
        return []
    present = {v for v in values if isinstance(v, str)}
    return [s for s in AMENITY_SLUGS if s in present]


def amenities_from_yad2(in_property: object, additional_details: object) -> list[str]:
    """Derive our amenity slugs from a Yad2 listing's structured fields."""
    found: set[str] = set()

    ip = in_property if isinstance(in_property, dict) else {}
    for yad2_key, slug in _YAD2_INPROPERTY.items():
        if ip.get(yad2_key) is True:
            found.add(slug)

    # Some ads carry the count but not the matching `inProperty` flag.
    ad = additional_details if isinstance(additional_details, dict) else {}
    if _positive_count(ad.get("parkingSpacesCount")):
        found.add("parking")
    if _positive_count(ad.get("balconiesCount")):
        found.add("balcony")

    return [s for s in AMENITY_SLUGS if s in found]
