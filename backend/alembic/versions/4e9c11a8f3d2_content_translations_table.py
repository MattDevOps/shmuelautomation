"""content_translations table

Revision ID: 4e9c11a8f3d2
Revises: 7e2c4ab1d930
Create Date: 2026-05-14 13:03:59.001567

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4e9c11a8f3d2"
down_revision: str | Sequence[str] | None = "7e2c4ab1d930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_translations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("content_slug", sa.String(255), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "content_type",
            "content_slug",
            "lang",
            "field",
            name="uq_content_translations_lookup",
        ),
    )
    op.create_index(
        "ix_content_translations_content_type",
        "content_translations",
        ["content_type"],
    )
    op.create_index(
        "ix_content_translations_content_slug",
        "content_translations",
        ["content_slug"],
    )
    op.create_index(
        "ix_content_translations_lang",
        "content_translations",
        ["lang"],
    )
    op.create_index(
        "ix_content_translations_lookup",
        "content_translations",
        ["content_type", "content_slug", "lang"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_translations_lookup", table_name="content_translations")
    op.drop_index("ix_content_translations_lang", table_name="content_translations")
    op.drop_index("ix_content_translations_content_slug", table_name="content_translations")
    op.drop_index("ix_content_translations_content_type", table_name="content_translations")
    op.drop_table("content_translations")
