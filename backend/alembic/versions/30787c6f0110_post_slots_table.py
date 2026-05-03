"""post_slots table

Revision ID: 30787c6f0110
Revises: ccee99097fbc
Create Date: 2026-05-03 09:46:05.951954

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "30787c6f0110"
down_revision: str | Sequence[str] | None = "ccee99097fbc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "property_id",
            sa.Uuid(),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "posted",
                "skipped",
                "cancelled",
                name="post_slot_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_post_slots_property_id", "post_slots", ["property_id"])
    op.create_index("ix_post_slots_scheduled_for", "post_slots", ["scheduled_for"])
    op.create_index("ix_post_slots_status", "post_slots", ["status"])
    op.create_index(
        "ix_post_slots_status_scheduled",
        "post_slots",
        ["status", "scheduled_for"],
    )


def downgrade() -> None:
    op.drop_index("ix_post_slots_status_scheduled", table_name="post_slots")
    op.drop_index("ix_post_slots_status", table_name="post_slots")
    op.drop_index("ix_post_slots_scheduled_for", table_name="post_slots")
    op.drop_index("ix_post_slots_property_id", table_name="post_slots")
    op.drop_table("post_slots")
