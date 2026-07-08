"""Metacognitive loop — cognitive_repair_intentions (evidence-tiered failure
signatures Shree intends to repair).

Revision ID: 20260708_0002
Revises: 20260708_0001
Create Date: 2026-07-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260708_0002"
down_revision = "20260708_0001"
branch_labels = None
depends_on = None


def _big_id() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "cognitive_repair_intentions",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("signature", sa.String(160), nullable=False, unique=True),
        sa.Column("evidence_tier", sa.Integer(), server_default="4"),
        sa.Column("fix_class", sa.String(24), server_default="unknown"),
        sa.Column("recurrence", sa.Integer(), server_default="1"),
        sa.Column("guardian_involved", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("people", sa.Text(), nullable=True),
        sa.Column("sample", sa.Text(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(24), server_default="observing"),
        sa.Column("first_seen", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("repaired_at", sa.DateTime(), nullable=True),
        sa.Column("repair_note", sa.Text(), nullable=True),
    )
    op.create_index("idx_repair_status_tier", "cognitive_repair_intentions",
                    ["status", "evidence_tier"])


def downgrade() -> None:
    op.drop_index("idx_repair_status_tier",
                  table_name="cognitive_repair_intentions")
    op.drop_table("cognitive_repair_intentions")
