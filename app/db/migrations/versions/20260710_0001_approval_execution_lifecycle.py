"""Single-use approval execution lifecycle.

Revision ID: 20260710_0001
Revises: 20260709_0001
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260710_0001"
down_revision = "20260709_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cognitive_approvals") as batch:
        batch.add_column(sa.Column("execution_started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("execution_completed_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_cognitive_approvals_status", ["status"])


def downgrade() -> None:
    # Never turn a consumed authorization back into an executable approval.
    op.execute(
        sa.text(
            "UPDATE cognitive_approvals SET status = 'rejected' "
            "WHERE status IN ('executing', 'succeeded', 'failed', 'superseded')"
        )
    )
    with op.batch_alter_table("cognitive_approvals") as batch:
        batch.drop_index("ix_cognitive_approvals_status")
        batch.drop_column("execution_completed_at")
        batch.drop_column("execution_started_at")
