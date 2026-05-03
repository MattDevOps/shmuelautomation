"""cloud connections, photos, oauth states

Revision ID: 237b1761528b
Revises: bb70b28a0351
Create Date: 2026-05-03 08:22:21.985169

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "237b1761528b"
down_revision: str | Sequence[str] | None = "bb70b28a0351"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False, unique=True),
        sa.Column("account_email", sa.String(320), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("root_folder_id", sa.String(200), nullable=True),
        sa.Column("root_folder_name", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "cloud_photos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "property_id",
            sa.Uuid(),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("folder_external_id", sa.String(200), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("web_view_url", sa.String(500), nullable=True),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "property_id", "checksum", name="uq_cloud_photos_property_checksum"
        ),
    )
    op.create_index("ix_cloud_photos_property_id", "cloud_photos", ["property_id"])
    op.create_index("ix_cloud_photos_checksum", "cloud_photos", ["checksum"])

    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("state", sa.String(64), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_oauth_states_state", "oauth_states", ["state"])


def downgrade() -> None:
    op.drop_index("ix_oauth_states_state", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("ix_cloud_photos_checksum", table_name="cloud_photos")
    op.drop_index("ix_cloud_photos_property_id", table_name="cloud_photos")
    op.drop_table("cloud_photos")
    op.drop_table("cloud_connections")
