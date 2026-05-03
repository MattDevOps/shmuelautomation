"""property_notes table

Revision ID: 5a7a0cda510b
Revises: 144d719a89f9
Create Date: 2026-05-03 16:14:40.713071

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5a7a0cda510b"
down_revision: str | Sequence[str] | None = "144d719a89f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "property_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        op.f("ix_property_notes_property_id"),
        "property_notes",
        ["property_id"],
    )
    op.create_index(
        op.f("ix_property_notes_created_at"),
        "property_notes",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_property_notes_created_at"), table_name="property_notes")
    op.drop_index(op.f("ix_property_notes_property_id"), table_name="property_notes")
    op.drop_table("property_notes")
