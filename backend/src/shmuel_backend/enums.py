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


class GroupPlatform(StrEnum):
    WHATSAPP = "whatsapp"
    WHATSAPP_STATUS = "whatsapp_status"
    FACEBOOK = "facebook"
    JANGLO = "janglo"
    OTHER = "other"


class GroupAudience(StrEnum):
    """Which property types this group accepts."""

    RENT = "rent"
    SALE = "sale"
    BOTH = "both"


class SubscriberPreference(StrEnum):
    """Which property types a newsletter subscriber wants to hear about."""

    RENT = "rent"
    SALE = "sale"
    BOTH = "both"


class ThreadMode(StrEnum):
    """Who's driving replies on a 1:1 WhatsApp thread.

    BOT — chatbot answers eligible messages. HUMAN — bot is silent;
    Shmuel handles the thread manually. Flips back to BOT only when an
    admin clicks "release".
    """

    BOT = "bot"
    HUMAN = "human"


class ChatbotIntent(StrEnum):
    """Output of the intent classifier — drives the reply path.

    SEARCH — lead is asking for properties matching some criteria.
    QUESTION — off-catalog question that needs Shmuel personally.
    GREETING — hello/intro with no actionable ask yet.
    OTHER — anything else; treat as takeover so a human handles it.
    """

    SEARCH = "search"
    QUESTION = "question"
    GREETING = "greeting"
    OTHER = "other"
