import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from shmuel_backend.enums import BrokerFeeStatus, PropertyStatus, PropertyType


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


class CloudConnectionStatus(BaseModel):
    provider: str
    connected: bool
    account_email: str | None = None
    root_folder_name: str | None = None


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
