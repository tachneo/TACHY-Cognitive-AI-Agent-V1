"""Autonomous tasks — the self-triggering loop.

Revision ID: 20260709_0001
Revises: 20260708_0001
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260709_0001"
down_revision = "20260708_0002"
branch_labels = None
depends_on = None


def _big_id() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "cognitive_autonomous_tasks",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("handler", sa.String(32), nullable=False),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("at_time_hhmm", sa.String(5), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("runs_today", sa.Integer(), server_default="0"),
        sa.Column("run_date", sa.String(10), nullable=True),
        sa.Column("total_runs", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("created_by", sa.String(16), server_default="shree"),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_at_status_next", "cognitive_autonomous_tasks",
                    ["status", "next_run_at"])
    op.create_index("idx_at_handler", "cognitive_autonomous_tasks",
                    ["handler"])


def downgrade() -> None:
    op.drop_index("idx_at_handler", table_name="cognitive_autonomous_tasks")
    op.drop_index("idx_at_status_next", table_name="cognitive_autonomous_tasks")
    op.drop_table("cognitive_autonomous_tasks")
