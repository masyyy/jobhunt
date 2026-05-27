"""Add pgvector extension and document_chunks table.

Revision ID: 006
Revises: 005
Create Date: 2026-05-05

Enables the pgvector extension and adds a document_chunks table that stores
embeddings for files under DOCUMENTS_DIR. Used by the search_files tool and
the index-documents background task. Each row points to a file path and an
optional page range; embeddings are 1536-dim (text-embedding-3-large with
Matryoshka truncation).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("file_mtime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_chunks_file_path", "document_chunks", ["file_path"])
    # HNSW works well on empty/sparse tables (unlike ivfflat, which needs data
    # at index creation to train its lists). m/ef_construction defaults are fine
    # for the expected scale (low thousands of chunks).
    op.execute("CREATE INDEX ix_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
    op.drop_index("ix_document_chunks_file_path", table_name="document_chunks")
    op.drop_table("document_chunks")
