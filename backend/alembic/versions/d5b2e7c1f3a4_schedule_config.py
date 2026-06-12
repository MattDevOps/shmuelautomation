"""schedule_config table

Revision ID: d5b2e7c1f3a4
Revises: c4f8a02e1d09
Create Date: 2026-06-12

DB-backed posting schedule so the slot times, capacity, and Shabbat window
are editable from the admin without a redeploy.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5b2e7c1f3a4"
down_revision: str | Sequence[str] | None = "c4f8a02e1d09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_config",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "timezone", sa.String(64), nullable=False, server_default="Asia/Jerusalem"
        ),
        sa.Column("morning_slot", sa.String(5), nullable=False, server_default="08:00"),
        sa.Column("evening_slot", sa.String(5), nullable=False, server_default="20:00"),
        sa.Column("posts_per_slot", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "friday_block_after", sa.String(5), nullable=False, server_default="13:00"
        ),
        sa.Column(
            "saturday_resume_at", sa.String(5), nullable=False, server_default="21:00"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("schedule_config")
