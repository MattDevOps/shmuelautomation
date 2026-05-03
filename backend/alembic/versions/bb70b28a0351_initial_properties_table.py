"""initial properties table

Revision ID: bb70b28a0351
Revises:
Create Date: 2026-05-03 07:35:39.945209

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bb70b28a0351"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "type",
            sa.Enum("rent", "sale", name="property_type", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "available",
                "rented",
                "sold",
                name="property_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rooms", sa.Numeric(3, 1), nullable=True),
        sa.Column("size_sqm", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("neighborhood", sa.String(200), nullable=True),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("owner_name", sa.String(200), nullable=True),
        sa.Column("owner_phone", sa.String(50), nullable=True),
        sa.Column(
            "broker_fee_status",
            sa.Enum(
                "yes",
                "no",
                "partial",
                name="broker_fee_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("broker_fee_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("yad2_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_properties_type", "properties", ["type"])
    op.create_index("ix_properties_status", "properties", ["status"])
    op.create_index("ix_properties_neighborhood", "properties", ["neighborhood"])
    op.create_index("ix_properties_type_status", "properties", ["type", "status"])


def downgrade() -> None:
    op.drop_index("ix_properties_type_status", table_name="properties")
    op.drop_index("ix_properties_neighborhood", table_name="properties")
    op.drop_index("ix_properties_status", table_name="properties")
    op.drop_index("ix_properties_type", table_name="properties")
    op.drop_table("properties")
