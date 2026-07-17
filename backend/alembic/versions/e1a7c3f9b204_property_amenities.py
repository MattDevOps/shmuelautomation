"""property amenities column

Revision ID: e1a7c3f9b204
Revises: d5b2e7c1f3a4
Create Date: 2026-07-17 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a7c3f9b204"
down_revision: str | Sequence[str] | None = "d5b2e7c1f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default '[]' so existing rows read back as an empty list rather
    # than NULL (mirrors contacts.segments).
    op.add_column(
        "properties",
        sa.Column("amenities", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("properties", "amenities")
