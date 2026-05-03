import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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
from shmuel_backend.enums import BrokerFeeStatus, PropertyStatus, PropertyType


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


class OAuthState(Base):
    """Short-lived CSRF state for OAuth flows. Single-use; deleted on callback."""

    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
