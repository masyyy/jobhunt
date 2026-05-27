"""Add jobs table for scraped Finnish job postings.

Revision ID: 007
Revises: 006
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("employer", sa.String(500), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_jobs_source_external_id", "jobs", ["source", "external_id"])
    op.create_index("ix_jobs_category", "jobs", ["category"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_posted_at", "jobs", ["posted_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_posted_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_category", table_name="jobs")
    op.drop_constraint("uq_jobs_source_external_id", "jobs", type_="unique")
    op.drop_table("jobs")
