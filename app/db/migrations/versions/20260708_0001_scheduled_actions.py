"""Prospective memory — scheduled_actions table.

Revision ID: 20260708_0001
Revises: 20260627_0001
Create Date: 2026-07-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260708_0001"
down_revision = "20260627_0001"
branch_labels = None
depends_on = None


def _big_id() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "cognitive_scheduled_actions",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("source_message_id", sa.String(255), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("person", sa.String(255), nullable=True),
        sa.Column("status", sa.String(24), server_default="pending"),
        sa.Column("actor", sa.String(64), server_default="gemma-intent"),
        sa.Column("approval_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("fired_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_status_due", "cognitive_scheduled_actions",
                    ["status", "due_at"])
    op.create_index("idx_conversation", "cognitive_scheduled_actions",
                    ["conversation_id"])


def downgrade() -> None:
    op.drop_index("idx_conversation", table_name="cognitive_scheduled_actions")
    op.drop_index("idx_status_due", table_name="cognitive_scheduled_actions")
    op.drop_table("cognitive_scheduled_actions")
