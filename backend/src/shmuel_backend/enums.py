from enum import StrEnum


class PropertyType(StrEnum):
    RENT = "rent"
    SALE = "sale"


class PropertyStatus(StrEnum):
    AVAILABLE = "available"
    RENTED = "rented"
    SOLD = "sold"


class BrokerFeeStatus(StrEnum):
    YES = "yes"
    NO = "no"
    PARTIAL = "partial"


class PostSlotStatus(StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"  # property went rented/sold or was deleted
