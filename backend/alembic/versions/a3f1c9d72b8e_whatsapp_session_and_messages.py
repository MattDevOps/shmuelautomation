"""whatsapp_session + whatsapp_messages tables

Revision ID: a3f1c9d72b8e
Revises: 4e9c11a8f3d2
Create Date: 2026-05-16 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f1c9d72b8e"
down_revision: str | Sequence[str] | None = "4e9c11a8f3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_session",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("blob", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("chat_jid", sa.String(128), nullable=False),
        sa.Column("from_jid", sa.String(128), nullable=False),
        sa.Column("from_phone", sa.String(32), nullable=True),
        sa.Column("from_name", sa.String(200), nullable=True),
        sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("group_id", sa.String(128), nullable=True),
        sa.Column("group_name", sa.String(255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(16), nullable=True),
        sa.Column("wa_timestamp", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "chat_jid", "message_id", name="uq_whatsapp_messages_chat_id",
        ),
    )
    op.create_index(
        "ix_whatsapp_messages_message_id",
        "whatsapp_messages",
        ["message_id"],
    )
    op.create_index(
        "ix_whatsapp_messages_chat_jid",
        "whatsapp_messages",
        ["chat_jid"],
    )
    op.create_index(
        "ix_whatsapp_messages_from_phone",
        "whatsapp_messages",
        ["from_phone"],
    )
    op.create_index(
        "ix_whatsapp_messages_chat_created",
        "whatsapp_messages",
        ["chat_jid", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_messages_chat_created", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_from_phone", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_chat_jid", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_message_id", table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_session")
