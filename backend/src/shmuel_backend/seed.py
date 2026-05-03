"""Seed realistic-looking data for a fresh dev or staging environment.

Idempotent — exits without changes if any properties already exist. Never
runs automatically; invoke explicitly:

    uv run python -m shmuel_backend.seed

For production use the admin UI to create real listings instead.
"""
import asyncio
from decimal import Decimal

from sqlalchemy import select

from shmuel_backend.db import SessionLocal
from shmuel_backend.enums import (
    BrokerFeeStatus,
    GroupAudience,
    GroupPlatform,
    PropertyStatus,
    PropertyType,
)
from shmuel_backend.models import Contact, Group, Property
from shmuel_backend.queue_routes import enqueue_property

PROPERTIES: list[dict[str, object]] = [
    {
        "type": PropertyType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("3200000"),
        "rooms": Decimal("4"),
        "size_sqm": 95,
        "floor": 2,
        "address": "12 Emek Refaim",
        "neighborhood": "Baka",
        "owner_name": "Yossi Cohen",
        "owner_phone": "+972500000001",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": (
            "Bright 4-room top-floor apartment overlooking the train track "
            "promenade. Original Jerusalem stone, mid-renovation, ready in "
            "two months."
        ),
        "yad2_url": "https://www.yad2.co.il/realestate/item/sample-1",
    },
    {
        "type": PropertyType.RENT,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("8500"),
        "rooms": Decimal("3.5"),
        "size_sqm": 80,
        "floor": 1,
        "address": "12 Aza St",
        "neighborhood": "רחביה",
        "owner_name": "Dani Levi",
        "owner_phone": "+972500000002",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": "דירה מקסימה 3.5 חדרים בבניין שקט. גינה משותפת. מיידי.",
    },
    {
        "type": PropertyType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("4500000"),
        "rooms": Decimal("5"),
        "size_sqm": 140,
        "floor": 3,
        "address": "4 Kovshei Katamon",
        "neighborhood": "Old Katamon",
        "owner_name": "Sarah Williams",
        "broker_fee_status": BrokerFeeStatus.YES,
        "broker_fee_amount": Decimal("90000"),
        "description": (
            "Spacious 5-room family apartment with sukkah balcony, parking "
            "spot, machsan. Walking distance to synagogues and parks."
        ),
    },
    {
        "type": PropertyType.RENT,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("6200"),
        "rooms": Decimal("2"),
        "size_sqm": 55,
        "address": "8 Hagai St",
        "neighborhood": "Talpiot",
        "owner_name": "Avi Mizrahi",
        "owner_phone": "+972500000003",
        "broker_fee_status": BrokerFeeStatus.NO,
        "description": "Cosy 2-room ground-floor with private entrance. Suits a single or couple.",
    },
    {
        "type": PropertyType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("2750000"),
        "rooms": Decimal("3"),
        "size_sqm": 72,
        "floor": 4,
        "address": "20 Bezalel St",
        "neighborhood": "Nachlaot",
        "owner_name": "Hannah Goldberg",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": (
            "Renovated 3-room in the heart of Nachlaot. Modern kitchen, high "
            "ceilings, elevator. Investment opportunity or pied-à-terre."
        ),
    },
    {
        "type": PropertyType.RENT,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("11500"),
        "rooms": Decimal("4"),
        "size_sqm": 110,
        "floor": 2,
        "address": "5 Emek Refaim",
        "neighborhood": "German Colony",
        "owner_name": "Eitan Goldstein",
        "owner_phone": "+972500000004",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": "Furnished 4-room with private garden. Long-term tenant only.",
    },
    {
        "type": PropertyType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("5800000"),
        "rooms": Decimal("5.5"),
        "size_sqm": 165,
        "address": "Mamilla Mall area",
        "neighborhood": "Mamilla",
        "owner_name": "David Stern",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": (
            "Luxury 5.5-room with rooftop terrace and Old City views. "
            "Concierge building."
        ),
    },
    {
        "type": PropertyType.RENT,
        "status": PropertyStatus.RENTED,
        "price": Decimal("7200"),
        "rooms": Decimal("3"),
        "size_sqm": 65,
        "address": "7 Sderot Eshkol",
        "neighborhood": "French Hill",
        "owner_name": "Rachel Friedman",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": "Recently rented — kept here for the queue + history.",
    },
    {
        "type": PropertyType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("3950000"),
        "rooms": Decimal("4"),
        "size_sqm": 105,
        "floor": 2,
        "address": "33 King George",
        "neighborhood": "City Center",
        "owner_name": "Moshe Klein",
        "owner_phone": "+972500000005",
        "broker_fee_status": BrokerFeeStatus.PARTIAL,
        "description": "Central, walk to everything. Needs cosmetic refresh, priced accordingly.",
    },
    {
        "type": PropertyType.RENT,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("9200"),
        "rooms": Decimal("3.5"),
        "size_sqm": 88,
        "floor": 5,
        "address": "12 Hapalmach",
        "neighborhood": "Katamon",
        "owner_name": "Ronit Azulai",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": (
            "Top-floor with elevator and balcony, mountain views. "
            "Long-term lease preferred."
        ),
    },
    {
        "type": PropertyType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("2400000"),
        "rooms": Decimal("3"),
        "size_sqm": 68,
        "floor": 1,
        "address": "Yefe Nof",
        "neighborhood": "Bayit Vegan",
        "owner_name": "Shimon Levi",
        "broker_fee_status": BrokerFeeStatus.YES,
        "description": (
            "Garden-level 3-room near the Israel Museum. "
            "Quiet street, parking included."
        ),
    },
    {
        "type": PropertyType.RENT,
        "status": PropertyStatus.AVAILABLE,
        "price": Decimal("5400"),
        "rooms": Decimal("2"),
        "size_sqm": 50,
        "floor": 2,
        "address": "Yad Harutzim",
        "neighborhood": "Talpiot",
        "broker_fee_status": BrokerFeeStatus.NO,
        "description": "Studio-style 2-room near tech park. Furnished, suits a young professional.",
    },
]

CONTACTS: list[dict[str, object]] = [
    {
        "name": "Yossi Cohen",
        "phone": "+972500000001",
        "language": "he",
        "segments": ["buyer", "baka"],
        "notes": "Looking in Baka, budget 3.2M, two kids.",
        "source": "manual",
    },
    {
        "name": "דני לוי",
        "phone": "+972500000002",
        "language": "he",
        "segments": ["renter", "rehavia"],
        "notes": "מחפש 3.5 חדרים, רחביה / טלביה.",
        "source": "manual",
    },
    {
        "name": "Sarah Williams",
        "email": "sarah@example.com",
        "language": "en",
        "segments": ["buyer", "vip", "past-client"],
        "notes": "Bought a 5-room in Old Katamon last year; referral source.",
        "source": "manual",
    },
    {
        "name": "Avi Mizrahi",
        "phone": "+972500000003",
        "language": "he",
        "segments": ["landlord"],
        "notes": "Owns 3 properties in Talpiot, hands them to me when vacant.",
        "source": "manual",
    },
    {
        "name": "Hannah Goldberg",
        "email": "hannah@example.com",
        "phone": "+972500000099",
        "language": "en",
        "segments": ["buyer", "investor"],
        "notes": "Lives in NY, looking for an investment property under 3M.",
        "source": "manual",
    },
    {
        "name": "Eitan Goldstein",
        "phone": "+972500000004",
        "language": "he",
        "segments": ["landlord", "german-colony"],
        "notes": "Furnished long-term rentals only.",
        "source": "manual",
    },
    {
        "name": "David Stern",
        "email": "david.stern@example.com",
        "language": "en",
        "segments": ["buyer", "vip"],
        "notes": "High-end only, Mamilla / Old City views, no upper limit.",
        "source": "manual",
    },
    {
        "name": "Ronit Azulai",
        "phone": "+972500000098",
        "language": "he",
        "segments": ["landlord", "katamon"],
        "source": "manual",
    },
]

GROUPS: list[dict[str, object]] = [
    {
        "platform": GroupPlatform.WHATSAPP,
        "audience": GroupAudience.RENT,
        "name": "Jerusalem Rentals WA",
        "target_url": "https://chat.whatsapp.com/example-rentals",
        "sort_order": 0,
    },
    {
        "platform": GroupPlatform.WHATSAPP,
        "audience": GroupAudience.SALE,
        "name": "Jerusalem Sales WA",
        "target_url": "https://chat.whatsapp.com/example-sales",
        "sort_order": 0,
    },
    {
        "platform": GroupPlatform.FACEBOOK,
        "audience": GroupAudience.BOTH,
        "name": "Jerusalem Real Estate (FB)",
        "target_url": "https://facebook.com/groups/example",
        "sort_order": 0,
    },
    {
        "platform": GroupPlatform.JANGLO,
        "audience": GroupAudience.RENT,
        "name": "Janglo — Real Estate Rentals",
        "target_url": "https://www.janglo.net/classifieds",
        "sort_order": 0,
    },
]


async def seed() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(Property).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("Database already has properties; skipping seed.")
            return

        new_properties: list[Property] = []
        for payload in PROPERTIES:
            prop = Property(**payload)
            session.add(prop)
            new_properties.append(prop)
        await session.flush()  # populate ids before enqueue

        # Mirror the production flow: each available property gets a queue slot.
        slots_added = 0
        for prop in new_properties:
            if prop.status == PropertyStatus.AVAILABLE:
                await enqueue_property(session, prop.id, priority=200)
                slots_added += 1

        for payload in CONTACTS:
            session.add(Contact(**payload))
        for payload in GROUPS:
            session.add(Group(**payload))

        await session.commit()
        print(
            f"Seeded {len(PROPERTIES)} properties ({slots_added} queued), "
            f"{len(CONTACTS)} contacts, {len(GROUPS)} groups."
        )


if __name__ == "__main__":
    asyncio.run(seed())
