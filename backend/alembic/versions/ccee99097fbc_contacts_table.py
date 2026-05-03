"""contacts table

Revision ID: ccee99097fbc
Revises: 237b1761528b
Create Date: 2026-05-03 09:33:23.773175

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ccee99097fbc"
down_revision: str | Sequence[str] | None = "237b1761528b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("segments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
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
    op.create_index("ix_contacts_phone", "contacts", ["phone"])


def downgrade() -> None:
    op.drop_index("ix_contacts_phone", table_name="contacts")
    op.drop_table("contacts")
