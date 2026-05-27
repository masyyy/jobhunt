"""Add application_text column to jobs for the drafted cover letter.

Stores the LLM-drafted cover letter + how-to-apply note so reopening the Apply
dialog shows the saved draft instead of regenerating (and re-charging) every
time.

Revision ID: 010
Revises: 009
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("application_cover_letter", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("application_how_to_apply", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "application_how_to_apply")
    op.drop_column("jobs", "application_cover_letter")
