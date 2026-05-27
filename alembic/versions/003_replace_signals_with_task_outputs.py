"""Replace signals table with generic task_outputs.

Revision ID: 003
Revises: 002
Create Date: 2026-04-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_name", sa.String(100), nullable=False),
        sa.Column("toolbox", sa.String(50), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_task_outputs_task_name", "task_outputs", ["task_name"])
    op.create_index("ix_task_outputs_toolbox", "task_outputs", ["toolbox"])

    op.execute(
        """
        INSERT INTO task_outputs (id, task_name, toolbox, payload, created_at, expires_at)
        SELECT
            id,
            'generate-signals',
            toolbox,
            json_build_object(
                'title', title,
                'prompt', prompt,
                'severity', severity,
                'category', category,
                'state', state,
                'source', source
            ),
            created_at,
            expires_at
        FROM signals
        """
    )

    op.drop_index("ix_signals_toolbox", table_name="signals")
    op.drop_index("ix_signals_state", table_name="signals")
    op.drop_table("signals")


def downgrade() -> None:
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

    op.execute(
        """
        INSERT INTO signals (id, title, prompt, severity, category, state, toolbox, source, expires_at, created_at)
        SELECT
            id,
            COALESCE(payload->>'title', ''),
            COALESCE(payload->>'prompt', ''),
            COALESCE(payload->>'severity', 'medium'),
            COALESCE(payload->>'category', ''),
            COALESCE(payload->>'state', 'active'),
            toolbox,
            payload->>'source',
            expires_at,
            created_at
        FROM task_outputs
        WHERE task_name = 'generate-signals'
        """
    )

    op.drop_index("ix_task_outputs_toolbox", table_name="task_outputs")
    op.drop_index("ix_task_outputs_task_name", table_name="task_outputs")
    op.drop_table("task_outputs")
