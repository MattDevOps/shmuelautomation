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
