"""Add toolbox column to conversations table.

Revision ID: 002
Revises: 001
Create Date: 2026-04-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("toolbox", sa.String(50), nullable=True))
    op.create_index("ix_conversations_toolbox", "conversations", ["toolbox"])


def downgrade() -> None:
    op.drop_index("ix_conversations_toolbox", table_name="conversations")
    op.drop_column("conversations", "toolbox")
