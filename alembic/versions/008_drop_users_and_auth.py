"""Drop users table and conversations.user_id (auth removed).

Revision ID: 008
Revises: 007
Create Date: 2026-05-27

This is a single-user personal dashboard; Supabase auth and per-user scoping
were removed. Drops the conversations.user_id FK/index and the users table.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")
    op.drop_index("ux_users_email_active", table_name="users")
    op.drop_table("users")


def downgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False, server_default="regular"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'regular')", name="ck_users_role"),
    )
    op.create_index(
        "ux_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
