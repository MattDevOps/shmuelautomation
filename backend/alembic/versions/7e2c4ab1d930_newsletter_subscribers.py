"""newsletter_subscribers table

Revision ID: 7e2c4ab1d930
Revises: 5a7a0cda510b
Create Date: 2026-05-07 12:50:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7e2c4ab1d930"
down_revision: str | Sequence[str] | None = "5a7a0cda510b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column(
            "type_filter",
            sa.Enum(
                "rent",
                "sale",
                "both",
                name="subscriber_preference",
                native_enum=False,
                length=8,
            ),
            nullable=False,
            server_default="both",
        ),
        sa.Column("confirmation_token", sa.String(64), nullable=False),
        sa.Column("unsubscribe_token", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(), nullable=True),
        sa.Column("last_digest_at", sa.DateTime(), nullable=True),
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
    op.create_index(
        "ix_newsletter_subscribers_email",
        "newsletter_subscribers",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_newsletter_subscribers_confirmation_token",
        "newsletter_subscribers",
        ["confirmation_token"],
        unique=True,
    )
    op.create_index(
        "ix_newsletter_subscribers_unsubscribe_token",
        "newsletter_subscribers",
        ["unsubscribe_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_newsletter_subscribers_unsubscribe_token",
        table_name="newsletter_subscribers",
    )
    op.drop_index(
        "ix_newsletter_subscribers_confirmation_token",
        table_name="newsletter_subscribers",
    )
    op.drop_index(
        "ix_newsletter_subscribers_email",
        table_name="newsletter_subscribers",
    )
    op.drop_table("newsletter_subscribers")
