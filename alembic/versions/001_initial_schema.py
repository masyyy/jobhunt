"""Initial schema — conversations, messages, summaries, signals, ingestion log.

Revision ID: 001
Revises:
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- conversations ---
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # --- messages ---
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=True),
        sa.Column("assistant_text", sa.Text(), nullable=True),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    # --- conversation_summaries ---
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("covers_until_message_id", sa.String(36), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversation_summaries_conversation_id", "conversation_summaries", ["conversation_id"])

    # --- signals ---
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("toolbox", sa.String(50), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_signals_state", "signals", ["state"])
    op.create_index("ix_signals_toolbox", "signals", ["toolbox"])

    # --- ingestion_log ---
    op.create_table(
        "ingestion_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("delta_table", sa.String(255), nullable=False),
        sa.Column("delta_version", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("schema_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_log")
    op.drop_table("signals")
    op.drop_table("conversation_summaries")
    op.drop_table("messages")
    op.drop_table("conversations")
