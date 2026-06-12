import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shmuel_backend.enums import (
    BrokerFeeStatus,
    GroupAudience,
    GroupPlatform,
    PostSlotStatus,
    PropertyStatus,
    PropertyType,
)


class PropertyBase(BaseModel):
    type: PropertyType
    status: PropertyStatus = PropertyStatus.AVAILABLE
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="ILS", min_length=3, max_length=3)
    rooms: Decimal | None = Field(default=None, ge=0, max_digits=3, decimal_places=1)
    size_sqm: int | None = Field(default=None, ge=0)
    floor: int | None = None
    address: str | None = Field(default=None, max_length=500)
    neighborhood: str | None = Field(default=None, max_length=200)
    city: str = Field(default="Jerusalem", max_length=200)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_phone: str | None = Field(default=None, max_length=50)
    broker_fee_status: BrokerFeeStatus = BrokerFeeStatus.YES
    broker_fee_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    description: str | None = None
    notes: str | None = None
    yad2_url: str | None = Field(default=None, max_length=500)


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: PropertyType | None = None
    status: PropertyStatus | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    rooms: Decimal | None = Field(default=None, ge=0, max_digits=3, decimal_places=1)
    size_sqm: int | None = Field(default=None, ge=0)
    floor: int | None = None
    address: str | None = Field(default=None, max_length=500)
    neighborhood: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=200)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_phone: str | None = Field(default=None, max_length=50)
    broker_fee_status: BrokerFeeStatus | None = None
    broker_fee_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    description: str | None = None
    notes: str | None = None
    yad2_url: str | None = Field(default=None, max_length=500)


class PropertyRead(PropertyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Yad2ImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class PostSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    scheduled_for: datetime
    status: PostSlotStatus
    priority: int
    posted_at: datetime | None = None
    created_at: datetime


class PostSlotWithProperty(PostSlotRead):
    """A queue row for the admin UI — includes the property snippet so the
    page can render a row without an extra fetch per item."""

    property_type: PropertyType
    property_neighborhood: str | None = None
    property_address: str | None = None
    property_price: Decimal


_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class ScheduleConfigRead(BaseModel):
    timezone: str
    morning_slot: str
    evening_slot: str
    posts_per_slot: int
    friday_block_after: str
    saturday_resume_at: str


class ScheduleConfigUpdate(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)
    morning_slot: str = Field(pattern=_HHMM)
    evening_slot: str = Field(pattern=_HHMM)
    posts_per_slot: int = Field(ge=1, le=50)
    friday_block_after: str = Field(pattern=_HHMM)
    saturday_resume_at: str = Field(pattern=_HHMM)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {v}") from exc
        return v


class PostCompose(BaseModel):
    text_en: str
    text_he: str
    whatsapp_share_url: str
    facebook_share_url: str | None = None
    # True when the property has photos, so the UI can offer a collage preview.
    has_collage: bool = False


class PublicPhoto(BaseModel):
    thumbnail_url: str | None = None
    web_view_url: str | None = None
    file_name: str


class PublicProperty(BaseModel):
    """Public listing payload — no owner PII, no internal notes, no broker terms."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: PropertyType
    status: PropertyStatus
    price: Decimal
    currency: str
    rooms: Decimal | None = None
    size_sqm: int | None = None
    floor: int | None = None
    address: str | None = None
    neighborhood: str | None = None
    city: str
    description: str | None = None
    yad2_url: str | None = None
    photos: list[PublicPhoto] = []
    created_at: datetime
    updated_at: datetime


class PublicPropertyList(BaseModel):
    items: list[PublicProperty]
    total: int
    limit: int
    offset: int


class ContactBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=320)
    language: str | None = Field(default=None, max_length=8)
    segments: list[str] = Field(default_factory=list)
    notes: str | None = None
    source: str | None = Field(default=None, max_length=50)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=320)
    language: str | None = Field(default=None, max_length=8)
    segments: list[str] | None = None
    notes: str | None = None
    source: str | None = Field(default=None, max_length=50)


class ContactRead(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ContactMatch(BaseModel):
    """Contact matched against a property's type/neighborhood.

    `match_score` is 2 when both audience-intent and neighborhood match,
    1 when just one. Frontend orders by score desc and shows reasons so
    Shmuel can see *why* a contact came up.
    """

    id: uuid.UUID
    name: str
    phone: str | None = None
    email: str | None = None
    segments: list[str]
    match_score: int
    match_reasons: list[str]


class DuplicateMatch(BaseModel):
    """Slim payload for the inline 'looks like a duplicate' warning."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: PropertyType
    status: PropertyStatus
    price: Decimal
    currency: str
    neighborhood: str | None = None
    address: str | None = None


class BulkStatusUpdate(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    status: PropertyStatus


class BulkDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class PropertyNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class PropertyNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    body: str
    created_at: datetime


class BulkResult(BaseModel):
    """Same shape for both bulk-status and bulk-delete: how many rows we
    actually touched, and which ids we couldn't find. The frontend uses
    `not_found` to surface partial failures so Shmuel knows e.g. a row
    was already deleted in another tab."""

    affected: int
    not_found: list[uuid.UUID] = []


class GroupBase(BaseModel):
    platform: GroupPlatform
    audience: GroupAudience = GroupAudience.BOTH
    name: str = Field(min_length=1, max_length=200)
    target_url: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    sort_order: int = 0
    active: bool = True


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: GroupPlatform | None = None
    audience: GroupAudience | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    target_url: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    sort_order: int | None = None
    active: bool | None = None


class GroupRead(GroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CloudConnectionStatus(BaseModel):
    provider: str
    connected: bool
    account_email: str | None = None
    root_folder_name: str | None = None


class SystemStatus(BaseModel):
    """Aggregated system health for the admin /system page.

    What Shmuel needs to self-diagnose 'is the system OK' before calling.
    Cheap — a handful of indexed SELECTs. Don't expose secrets here.
    """

    environment: str
    db_ok: bool
    drive_connected: bool
    drive_account_email: str | None = None
    queue_pending_count: int
    queue_due_now_count: int
    properties_available: int
    properties_total: int
    contacts_count: int
    groups_active: int


class CloudPhotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    provider: str
    external_id: str
    folder_external_id: str
    file_name: str
    mime_type: str
    size_bytes: int
    web_view_url: str | None = None
    thumbnail_url: str | None = None
    created_at: datetime


class PropertyPhotoSummary(BaseModel):
    property_id: uuid.UUID
    count: int
    # ID of the most-recent photo, used by the list page to build a
    # fresh-thumbnail URL (/properties/{pid}/photos/{first_photo_id}/thumbnail).
    first_photo_id: uuid.UUID | None = None
    # Kept for backward compatibility; the stored Drive thumbnailLink expires
    # after hours and can't be hotlinked, so the UI no longer renders it.
    first_thumbnail: str | None = None


class Yad2ImportPreview(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    price: str | None = None
    rooms: str | None = None
    size_sqm: int | None = None
    floor: int | None = None
    address: str | None = None
    neighborhood: str | None = None
    image_urls: list[str] = []
    warnings: list[str] = []
