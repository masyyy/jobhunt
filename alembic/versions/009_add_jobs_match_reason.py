"""Add match_reason column to jobs for the LLM matcher's justification.

Revision ID: 009
Revises: 008
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("match_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "match_reason")
