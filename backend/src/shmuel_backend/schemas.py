import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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


class PostCompose(BaseModel):
    text_en: str
    text_he: str
    whatsapp_share_url: str
    facebook_share_url: str | None = None


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
