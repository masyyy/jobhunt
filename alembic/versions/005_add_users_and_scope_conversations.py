"""Add users table and scope conversations by user_id.

Revision ID: 005
Revises: 004
Create Date: 2026-04-27

Adds the application users table (id matches Supabase Auth user UUID) and a
nullable user_id FK on conversations. Existing conversation rows keep
user_id = NULL; the API layer treats them as inaccessible after this migration.
A follow-up migration can enforce NOT NULL once the table is fully scoped.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        # Email uniqueness is enforced via the partial index ux_users_email_active
        # below — only active rows must be unique. Soft-deleted tombstones keep
        # their original email so a future invite for the same address can succeed.
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


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")
    op.drop_index("ux_users_email_active", table_name="users")
    op.drop_table("users")
