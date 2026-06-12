import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shmuel_backend.db import Base
from shmuel_backend.enums import (
    BrokerFeeStatus,
    GroupAudience,
    GroupPlatform,
    PostSlotStatus,
    PropertyStatus,
    PropertyType,
    SubscriberPreference,
    ThreadMode,
)


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    type: Mapped[PropertyType] = mapped_column(
        Enum(PropertyType, name="property_type", native_enum=False, length=16),
        index=True,
    )
    status: Mapped[PropertyStatus] = mapped_column(
        Enum(PropertyStatus, name="property_status", native_enum=False, length=16),
        default=PropertyStatus.AVAILABLE,
        index=True,
    )

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="ILS")

    rooms: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    size_sqm: Mapped[int | None] = mapped_column()
    floor: Mapped[int | None] = mapped_column()

    address: Mapped[str | None] = mapped_column(String(500))
    neighborhood: Mapped[str | None] = mapped_column(String(200), index=True)
    city: Mapped[str] = mapped_column(String(200), default="Jerusalem")

    owner_name: Mapped[str | None] = mapped_column(String(200))
    owner_phone: Mapped[str | None] = mapped_column(String(50))

    broker_fee_status: Mapped[BrokerFeeStatus] = mapped_column(
        Enum(BrokerFeeStatus, name="broker_fee_status", native_enum=False, length=16),
        default=BrokerFeeStatus.YES,
    )
    broker_fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    yad2_url: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("ix_properties_type_status", "type", "status"),)


class PropertyNote(Base):
    """A dated free-form entry in a property's timeline.

    Distinct from `Property.notes` (which is a single static text blob).
    These are sequenced events: "called landlord — available end of
    month", "showing 4pm with Cohens", "price reduced to 3.1M". Newest
    first in the UI; deleting cascades from the parent property.
    """

    __tablename__ = "property_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class CloudConnection(Base):
    """A persistent OAuth connection to a cloud-storage provider.

    Single row per provider. The refresh token is encrypted at rest.
    """

    __tablename__ = "cloud_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), unique=True)
    account_email: Mapped[str | None] = mapped_column(String(320))
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    root_folder_id: Mapped[str | None] = mapped_column(String(200))
    root_folder_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class CloudPhoto(Base):
    """A photo file stored on the user's cloud account.

    `external_id` is the provider's file id (e.g. Drive file id).
    `checksum` makes uploads idempotent — re-posting the same file is a no-op.
    """

    __tablename__ = "cloud_photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(200))
    folder_external_id: Mapped[str] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    web_view_url: Mapped[str | None] = mapped_column(String(500))
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    property: Mapped[Property] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "property_id", "checksum", name="uq_cloud_photos_property_checksum"
        ),
    )


class Contact(Base):
    """A person in the broker's address book.

    Segments are a free-form list of tags (e.g. ['buyer', 'rehavia', 'vip']).
    Stored as JSON for portability across Postgres and SQLite. For Phase 1 we
    filter via simple SQL JSON operators; if querying gets complex later,
    promote to a join table without a public API change.
    """

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    language: Mapped[str | None] = mapped_column(String(8))
    segments: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class PostSlot(Base):
    """A scheduled posting opportunity for a property.

    The scheduler computes `scheduled_for` at create time and stores it as
    UTC. Status moves pending → posted (admin pressed "share") or skipped /
    cancelled. We never auto-fire posts — the queue is computed on demand
    when the admin opens the dashboard, then the admin taps share for each.
    """

    __tablename__ = "post_slots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[PostSlotStatus] = mapped_column(
        Enum(PostSlotStatus, name="post_slot_status", native_enum=False, length=16),
        default=PostSlotStatus.PENDING,
        index=True,
    )
    priority: Mapped[int] = mapped_column(default=100)
    posted_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    property: Mapped[Property] = relationship()

    __table_args__ = (
        Index("ix_post_slots_status_scheduled", "status", "scheduled_for"),
    )


class Group(Base):
    """A configurable destination for property posts.

    Examples: a Facebook rental group called 'Jerusalem Apartments For Rent',
    a WhatsApp group 'Baka Real Estate', or 'My WhatsApp Status'. Shmuel
    manages this list from the admin so he can reorder, rename, or disable
    groups without code changes.
    """

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    platform: Mapped[GroupPlatform] = mapped_column(
        Enum(GroupPlatform, name="group_platform", native_enum=False, length=24),
        index=True,
    )
    audience: Mapped[GroupAudience] = mapped_column(
        Enum(GroupAudience, name="group_audience", native_enum=False, length=8),
        default=GroupAudience.BOTH,
    )
    name: Mapped[str] = mapped_column(String(200))
    target_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_groups_platform_audience", "platform", "audience"),
    )


class NewsletterSubscriber(Base):
    """Public-site newsletter signup.

    Double opt-in: a row exists from the moment someone hits subscribe but
    `confirmed_at` is null until they click the email link. Digests only go
    to confirmed, non-unsubscribed rows. `last_digest_at` is the watermark
    for "what have we already sent this person" — properties created after
    that timestamp count toward the next digest.
    """

    __tablename__ = "newsletter_subscribers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    type_filter: Mapped[SubscriberPreference] = mapped_column(
        Enum(SubscriberPreference, name="subscriber_preference", native_enum=False, length=8),
        default=SubscriberPreference.BOTH,
    )
    confirmation_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column()
    unsubscribed_at: Mapped[datetime | None] = mapped_column()
    last_digest_at: Mapped[datetime | None] = mapped_column()
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class OAuthState(Base):
    """Short-lived CSRF state for OAuth flows. Single-use; deleted on callback."""

    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WhatsappSession(Base):
    """Persisted Baileys auth state for the WhatsApp daemon.

    Single-row table — the daemon writes the JSON-serialized
    `{creds, keys}` blob (base64-encoded) here on every state change and
    reads it on boot. Survives daemon redeploys so we don't have to
    rescan the QR every time.

    The blob is opaque to the backend; only the daemon ever interprets it.
    """

    __tablename__ = "whatsapp_session"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    blob: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class WhatsappMessage(Base):
    """Every inbound WhatsApp message the daemon forwards to us.

    Powers Phase 3.1 (chatbot decides what to reply) and Phase 3.2
    (nightly summarization into CRM notes). Keyed by WhatsApp's own
    message_id within a chat to make the daemon→backend webhook
    idempotent on retries.
    """

    __tablename__ = "whatsapp_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[str] = mapped_column(String(64), index=True)
    chat_jid: Mapped[str] = mapped_column(String(128), index=True)
    from_jid: Mapped[str] = mapped_column(String(128))
    from_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    from_name: Mapped[str | None] = mapped_column(String(200))
    is_group: Mapped[bool] = mapped_column(default=False)
    group_id: Mapped[str | None] = mapped_column(String(128))
    group_name: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(16))
    # WhatsApp's own timestamp in unix seconds — what the daemon reports.
    wa_timestamp: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("chat_jid", "message_id", name="uq_whatsapp_messages_chat_id"),
        Index("ix_whatsapp_messages_chat_created", "chat_jid", "created_at"),
    )


class ContentTranslation(Base):
    """Translations of WP-sourced content (properties, blog posts, neighborhoods)
    into ES/FR/HE. One row per (content_type, content_slug, lang, field).

    `source_hash` is sha256 of the source English field value at translation time;
    sync uses it to detect when WP content has changed and re-translation is needed.
    """

    __tablename__ = "content_translations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # property | blog | neighborhood
    content_type: Mapped[str] = mapped_column(String(20), index=True)
    content_slug: Mapped[str] = mapped_column(String(255), index=True)
    lang: Mapped[str] = mapped_column(String(8), index=True)  # es | fr | he
    # title | description_p1 | description_p2 | more_info_0 | ...
    field: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "content_type", "content_slug", "lang", "field",
            name="uq_content_translations_lookup",
        ),
        Index(
            "ix_content_translations_lookup",
            "content_type", "content_slug", "lang",
        ),
    )


class WhatsappThread(Base):
    """Conversation state for a 1:1 WhatsApp thread.

    One row per `chat_jid` (which for DMs is `<phone>@s.whatsapp.net`).
    Group chats never get a thread row — the bot ignores them entirely.

    `mode` decides whether the chatbot answers (BOT) or stays out of the
    way (HUMAN). The classifier flips a thread to HUMAN as soon as it
    sees a message it shouldn't auto-answer; an admin flips it back to
    BOT via the takeover/release endpoint.

    `last_processed_wa_ts` is the watermark — only messages with a
    higher `wa_timestamp` are considered new for this thread. This
    makes message processing idempotent under retry.
    """

    __tablename__ = "whatsapp_threads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_jid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[ThreadMode] = mapped_column(
        Enum(ThreadMode, name="thread_mode", native_enum=False, length=8),
        default=ThreadMode.BOT,
        index=True,
    )
    takeover_reason: Mapped[str | None] = mapped_column(String(64))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    last_processed_wa_ts: Mapped[int | None] = mapped_column(BigInteger)
    last_bot_reply_at: Mapped[datetime | None] = mapped_column()
    last_message_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class BotConfig(Base):
    """Single-row runtime config for the WhatsApp chatbot.

    Lives in the DB (not env) so Shmuel can toggle the bot on/off from
    the admin without a redeploy. `id` is always 'default' — enforced
    via primary key, not a separate constraint, so upserts stay simple.
    """

    __tablename__ = "bot_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    chatbot_enabled: Mapped[bool] = mapped_column(default=False)
    greeting_he: Mapped[str | None] = mapped_column(Text)
    greeting_en: Mapped[str | None] = mapped_column(Text)
    takeover_notice_he: Mapped[str | None] = mapped_column(Text)
    takeover_notice_en: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class ConversationSummary(Base):
    """LLM-summarized rollup of a WhatsApp thread for the CRM.

    Phase 3.2: a nightly job groups `whatsapp_messages` by `chat_jid`,
    summarizes the last 24h (or since the previous summary), and writes
    one row here per (chat_jid, day). `contact_id` is resolved at write
    time by phone-match against `contacts`.

    Idempotent on (chat_jid, period_end) — re-running the job for the
    same window updates rather than duplicates.
    """

    __tablename__ = "conversation_summaries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_jid: Mapped[str] = mapped_column(String(128), index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    period_start: Mapped[datetime] = mapped_column()
    period_end: Mapped[datetime] = mapped_column()
    message_count: Mapped[int] = mapped_column(default=0)
    summary: Mapped[str] = mapped_column(Text)
    action_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    mentioned_amounts: Mapped[list[str]] = mapped_column(JSON, default=list)
    mentioned_dates: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    __table_args__ = (
        UniqueConstraint(
            "chat_jid", "period_end", name="uq_conversation_summaries_period"
        ),
    )


class ScheduleConfig(Base):
    """Single-row runtime config for the posting schedule.

    Lives in the DB (not env) so Shmuel can change the daily slot times,
    per-slot capacity, and the Shabbat window from the admin without a
    redeploy. `id` is always 'default'. Times are 'HH:MM' strings in the
    configured timezone.
    """

    __tablename__ = "schedule_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Jerusalem")
    morning_slot: Mapped[str] = mapped_column(String(5), default="08:00")
    evening_slot: Mapped[str] = mapped_column(String(5), default="20:00")
    posts_per_slot: Mapped[int] = mapped_column(default=3)
    friday_block_after: Mapped[str] = mapped_column(String(5), default="13:00")
    saturday_resume_at: Mapped[str] = mapped_column(String(5), default="21:00")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
