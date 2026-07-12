"""agent runs

Revision ID: 0005_agent_runs
Revises: 0004_refresh_tokens
Create Date: 2026-07-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_agent_runs"
down_revision: str | None = "0004_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_status_enum = sa.Enum(
    "running", "completed", "failed", name="agent_run_status"
)


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("status", _status_enum, nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("answer_message_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["answer_message_id"], ["messages.id"],
                                ondelete="SET NULL"),
    )
    op.create_index(
        "ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_conversation_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    _status_enum.drop(op.get_bind(), checkfirst=True)
