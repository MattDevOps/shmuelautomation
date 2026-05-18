"""whatsapp_threads + bot_config + conversation_summaries

Revision ID: c4f8a02e1d09
Revises: a3f1c9d72b8e
Create Date: 2026-05-18 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4f8a02e1d09"
down_revision: str | Sequence[str] | None = "a3f1c9d72b8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_threads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("chat_jid", sa.String(128), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("mode", sa.String(8), nullable=False, server_default="bot"),
        sa.Column("takeover_reason", sa.String(64), nullable=True),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_processed_wa_ts", sa.BigInteger(), nullable=True),
        sa.Column("last_bot_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("chat_jid", name="uq_whatsapp_threads_chat_jid"),
    )
    op.create_index(
        "ix_whatsapp_threads_chat_jid", "whatsapp_threads", ["chat_jid"]
    )
    op.create_index(
        "ix_whatsapp_threads_phone_number", "whatsapp_threads", ["phone_number"]
    )
    op.create_index(
        "ix_whatsapp_threads_mode", "whatsapp_threads", ["mode"]
    )
    op.create_index(
        "ix_whatsapp_threads_contact_id", "whatsapp_threads", ["contact_id"]
    )

    op.create_table(
        "bot_config",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "chatbot_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("greeting_he", sa.Text(), nullable=True),
        sa.Column("greeting_en", sa.Text(), nullable=True),
        sa.Column("takeover_notice_he", sa.Text(), nullable=True),
        sa.Column("takeover_notice_en", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("chat_jid", sa.String(128), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=True),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "action_items",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "mentioned_amounts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "mentioned_dates",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "chat_jid", "period_end", name="uq_conversation_summaries_period"
        ),
    )
    op.create_index(
        "ix_conversation_summaries_chat_jid",
        "conversation_summaries",
        ["chat_jid"],
    )
    op.create_index(
        "ix_conversation_summaries_phone_number",
        "conversation_summaries",
        ["phone_number"],
    )
    op.create_index(
        "ix_conversation_summaries_contact_id",
        "conversation_summaries",
        ["contact_id"],
    )
    op.create_index(
        "ix_conversation_summaries_created_at",
        "conversation_summaries",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_summaries_created_at", table_name="conversation_summaries"
    )
    op.drop_index(
        "ix_conversation_summaries_contact_id", table_name="conversation_summaries"
    )
    op.drop_index(
        "ix_conversation_summaries_phone_number", table_name="conversation_summaries"
    )
    op.drop_index(
        "ix_conversation_summaries_chat_jid", table_name="conversation_summaries"
    )
    op.drop_table("conversation_summaries")

    op.drop_table("bot_config")

    op.drop_index("ix_whatsapp_threads_contact_id", table_name="whatsapp_threads")
    op.drop_index("ix_whatsapp_threads_mode", table_name="whatsapp_threads")
    op.drop_index(
        "ix_whatsapp_threads_phone_number", table_name="whatsapp_threads"
    )
    op.drop_index("ix_whatsapp_threads_chat_jid", table_name="whatsapp_threads")
    op.drop_table("whatsapp_threads")
