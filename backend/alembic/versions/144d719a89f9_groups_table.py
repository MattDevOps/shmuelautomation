"""groups table

Revision ID: 144d719a89f9
Revises: 30787c6f0110
Create Date: 2026-05-03 10:50:33.396568

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "144d719a89f9"
down_revision: str | Sequence[str] | None = "30787c6f0110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "platform",
            sa.Enum(
                "whatsapp",
                "whatsapp_status",
                "facebook",
                "janglo",
                "other",
                name="group_platform",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "audience",
            sa.Enum(
                "rent",
                "sale",
                "both",
                name="group_audience",
                native_enum=False,
                length=8,
            ),
            nullable=False,
            server_default="both",
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    op.create_index("ix_groups_platform", "groups", ["platform"])
    op.create_index(
        "ix_groups_platform_audience", "groups", ["platform", "audience"]
    )


def downgrade() -> None:
    op.drop_index("ix_groups_platform_audience", table_name="groups")
    op.drop_index("ix_groups_platform", table_name="groups")
    op.drop_table("groups")
