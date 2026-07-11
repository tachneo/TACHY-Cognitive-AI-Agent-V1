"""Self-module factory control-plane persistence.

Revision ID: 20260710_0002
Revises: 20260710_0001
Create Date: 2026-07-10

The tables in this revision hold proposals, immutable module versions,
capability grants, lifecycle audit events, surgery/canary observations, and
the evidence-backed self-model/task state.  Executable module artifacts remain
outside the database and outside the live application import path.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260710_0002"
down_revision = "20260710_0001"
branch_labels = None
depends_on = None


def _big_id() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "self_module_proposals",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("module_key", sa.String(120), nullable=False),
        sa.Column("module_name", sa.String(180), nullable=False),
        sa.Column("module_type", sa.String(80), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("weakness_detected", sa.Text(), nullable=False),
        sa.Column("expected_improvement", sa.Text(), nullable=False),
        sa.Column("proposed_by", sa.String(50), nullable=False),
        sa.Column("risk_level", sa.String(50), nullable=False),
        sa.Column("allowed_actions_json", sa.Text(), nullable=False),
        sa.Column("blocked_actions_json", sa.Text(), nullable=False),
        sa.Column("required_tests_json", sa.Text(), nullable=False),
        sa.Column("fallback_module_key", sa.String(120), nullable=True),
        sa.Column("rollback_plan", sa.Text(), nullable=False),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("evaluation_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("validation_report_json", sa.Text(), nullable=True),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "approval_request_id",
            _big_id(),
            sa.ForeignKey("cognitive_approvals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "module_type IN ('emotion','memory','reasoning','speech','tool','agent',"
            "'evaluator','safety_helper','business','erp','tody','curriculum',"
            "'self_model','other')",
            name="ck_self_module_proposals_module_type",
        ),
        sa.CheckConstraint(
            "proposed_by IN ('shree','rohit','system')",
            name="ck_self_module_proposals_proposed_by",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name="ck_self_module_proposals_risk_level",
        ),
        sa.CheckConstraint(
            "status IN ('draft','spec_created','coded','tested','failed_validation',"
            "'shadow','approval_pending','approved','canary_5','canary_25','active',"
            "'rejected','rolled_back')",
            name="ck_self_module_proposals_status",
        ),
        sa.CheckConstraint(
            "evaluation_score IS NULL OR (evaluation_score >= 0 AND evaluation_score <= 100)",
            name="ck_self_module_proposals_evaluation_score",
        ),
        sa.CheckConstraint(
            "version_counter >= 1",
            name="ck_self_module_proposals_version_counter",
        ),
    )
    op.create_index(
        "ix_self_module_proposals_module_key",
        "self_module_proposals",
        ["module_key"],
    )
    op.create_index(
        "ix_self_module_proposals_status_created",
        "self_module_proposals",
        ["status", "created_at"],
    )

    op.create_table(
        "self_modules",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("module_key", sa.String(120), nullable=False),
        sa.Column("module_name", sa.String(180), nullable=False),
        sa.Column("module_type", sa.String(80), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("active_version", sa.String(50), nullable=True),
        sa.Column("status", sa.String(80), nullable=False, server_default="inactive"),
        sa.Column("sandbox_path", sa.Text(), nullable=False),
        sa.Column("live_path", sa.Text(), nullable=True),
        sa.Column("allowed_actions_json", sa.Text(), nullable=False),
        sa.Column("blocked_actions_json", sa.Text(), nullable=False),
        sa.Column("health_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("last_eval_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("fallback_module_key", sa.String(120), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module_key", name="uq_self_modules_module_key"),
        sa.CheckConstraint(
            "module_type IN ('emotion','memory','reasoning','speech','tool','agent',"
            "'evaluator','safety_helper','business','erp','tody','curriculum',"
            "'self_model','other')",
            name="ck_self_modules_module_type",
        ),
        sa.CheckConstraint(
            "status IN ('inactive','shadow','canary_5','canary_25','active','failed',"
            "'rollback','disabled')",
            name="ck_self_modules_status",
        ),
        sa.CheckConstraint(
            "created_by IN ('shree','rohit','system')",
            name="ck_self_modules_created_by",
        ),
        sa.CheckConstraint(
            "health_score IS NULL OR (health_score >= 0 AND health_score <= 100)",
            name="ck_self_modules_health_score",
        ),
        sa.CheckConstraint(
            "last_eval_score IS NULL OR (last_eval_score >= 0 AND last_eval_score <= 100)",
            name="ck_self_modules_last_eval_score",
        ),
        sa.CheckConstraint(
            "version_counter >= 1",
            name="ck_self_modules_version_counter",
        ),
    )
    op.create_index("ix_self_modules_status", "self_modules", ["status"])
    op.create_index("ix_self_modules_module_type", "self_modules", ["module_type"])

    op.create_table(
        "module_versions",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("artifact_hash", sa.String(128), nullable=False),
        sa.Column("spec_path", sa.Text(), nullable=False),
        sa.Column("sandbox_path", sa.Text(), nullable=False),
        sa.Column("test_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("evaluation_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("validation_report_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module_key", "version", name="uq_module_versions_key_version"),
        sa.CheckConstraint(
            "status IN ('draft','testing','passed','failed','shadow','canary','active','archived')",
            name="ck_module_versions_status",
        ),
        sa.CheckConstraint(
            "evaluation_score IS NULL OR (evaluation_score >= 0 AND evaluation_score <= 100)",
            name="ck_module_versions_evaluation_score",
        ),
    )
    op.create_index("ix_module_versions_module_key", "module_versions", ["module_key"])
    op.create_index(
        "ix_module_versions_key_status",
        "module_versions",
        ["module_key", "status"],
    )

    op.create_table(
        "module_capability_envelopes",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("risk_level", sa.String(50), nullable=False),
        sa.Column("allowed_actions_json", sa.Text(), nullable=False),
        sa.Column("blocked_actions_json", sa.Text(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("filesystem_scope_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("network_scope_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("data_scope_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "approval_request_id",
            _big_id(),
            sa.ForeignKey("cognitive_approvals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("policy_hash", sa.String(128), nullable=False),
        sa.Column("policy_snapshot_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "module_key", "version", name="uq_module_capability_envelopes_key_version"
        ),
        sa.CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name="ck_module_capability_envelopes_risk_level",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','expired','revoked')",
            name="ck_module_capability_envelopes_status",
        ),
        sa.CheckConstraint(
            "created_by IN ('shree','rohit','system')",
            name="ck_module_capability_envelopes_created_by",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR valid_from IS NULL OR expires_at > valid_from",
            name="ck_module_capability_envelopes_validity",
        ),
        sa.CheckConstraint(
            "version_counter >= 1",
            name="ck_module_capability_envelopes_version_counter",
        ),
    )
    op.create_index(
        "ix_module_capability_envelopes_key_status",
        "module_capability_envelopes",
        ["module_key", "status"],
    )

    op.create_table(
        "module_control_logs",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("old_status", sa.String(80), nullable=True),
        sa.Column("new_status", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_module_control_logs_key_created",
        "module_control_logs",
        ["module_key", "created_at"],
    )

    op.create_table(
        "surgery_sessions",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("module_key", sa.String(120), nullable=False),
        sa.Column("from_version", sa.String(50), nullable=True),
        sa.Column("to_version", sa.String(50), nullable=False),
        sa.Column("surgery_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(80), nullable=False, server_default="planned"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("validation_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("health_before_json", sa.Text(), nullable=True),
        sa.Column("health_after_json", sa.Text(), nullable=True),
        sa.Column("rollback_plan", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column("policy_snapshot_hash", sa.String(128), nullable=False),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "surgery_type IN ('create','upgrade','patch','rollback','disable')",
            name="ck_surgery_sessions_type",
        ),
        sa.CheckConstraint(
            "status IN ('planned','isolated','testing','shadow','canary_5','canary_25',"
            "'promoted','rolled_back','failed')",
            name="ck_surgery_sessions_status",
        ),
        sa.CheckConstraint(
            "created_by IN ('shree','rohit','system')",
            name="ck_surgery_sessions_created_by",
        ),
        sa.CheckConstraint(
            "validation_score IS NULL OR (validation_score >= 0 AND validation_score <= 100)",
            name="ck_surgery_sessions_validation_score",
        ),
        sa.CheckConstraint(
            "version_counter >= 1",
            name="ck_surgery_sessions_version_counter",
        ),
    )
    op.create_index(
        "ix_surgery_sessions_key_status",
        "surgery_sessions",
        ["module_key", "status"],
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("eval_name", sa.String(180), nullable=False),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failures_json", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_evaluation_runs_score",
        ),
    )
    op.create_index(
        "ix_evaluation_runs_key_created",
        "evaluation_runs",
        ["module_key", "created_at"],
    )

    op.create_table(
        "module_shadow_runs",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("live_output_hash", sa.String(128), nullable=True),
        sa.Column("shadow_output_hash", sa.String(128), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("diff_json", sa.Text(), nullable=False),
        sa.Column("safety_flags_json", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_module_shadow_runs_score"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_module_shadow_runs_latency"),
    )
    op.create_index(
        "ix_module_shadow_runs_key_created",
        "module_shadow_runs",
        ["module_key", "created_at"],
    )

    op.create_table(
        "module_health_samples",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("health_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("error_rate", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("latency_p95_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("safety_violation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("privacy_leak_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("output_quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("user_correction_severity", sa.Integer(), nullable=True),
        sa.Column("prompt_injection_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "health_score >= 0 AND health_score <= 100",
            name="ck_module_health_samples_health_score",
        ),
        sa.CheckConstraint(
            "error_rate >= 0 AND error_rate <= 1",
            name="ck_module_health_samples_error_rate",
        ),
        sa.CheckConstraint(
            "latency_p95_ms >= 0 AND safety_violation_count >= 0 AND prompt_injection_failures >= 0",
            name="ck_module_health_samples_nonnegative",
        ),
        sa.CheckConstraint(
            "output_quality_score IS NULL OR (output_quality_score >= 0 AND output_quality_score <= 100)",
            name="ck_module_health_samples_output_quality",
        ),
        sa.CheckConstraint(
            "user_correction_severity IS NULL OR (user_correction_severity >= 0 AND user_correction_severity <= 10)",
            name="ck_module_health_samples_correction_severity",
        ),
    )
    op.create_index(
        "ix_module_health_samples_key_created",
        "module_health_samples",
        ["module_key", "created_at"],
    )

    op.create_table(
        "module_routes",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(120),
            sa.ForeignKey("self_modules.module_key"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("previous_version", sa.String(50), nullable=True),
        sa.Column("percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="inactive"),
        sa.Column("policy_snapshot_json", sa.Text(), nullable=False),
        sa.Column("policy_snapshot_hash", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("module_key", name="uq_module_routes_module_key"),
        sa.CheckConstraint(
            "percentage IN (0,5,25,100)",
            name="ck_module_routes_percentage",
        ),
        sa.CheckConstraint(
            "status IN ('inactive','shadow','canary_5','canary_25','active','failed',"
            "'rollback','disabled')",
            name="ck_module_routes_status",
        ),
        sa.CheckConstraint(
            "version_counter >= 1",
            name="ck_module_routes_version_counter",
        ),
    )
    op.create_index("ix_module_routes_status", "module_routes", ["status"])

    op.create_table(
        "self_model_events",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("event", sa.String(180), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("self_state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_self_model_events_confidence",
        ),
    )
    op.create_index("ix_self_model_events_created", "self_model_events", ["created_at"])

    op.create_table(
        "identity_reflection_logs",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("self_state_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("consistency_passed", sa.Boolean(), nullable=False),
        sa.Column("review_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_identity_reflection_logs_confidence",
        ),
    )
    op.create_index(
        "ix_identity_reflection_logs_created",
        "identity_reflection_logs",
        ["created_at"],
    )

    op.create_table(
        "cognitive_task_contexts",
        sa.Column("id", _big_id(), primary_key=True, autoincrement=True),
        sa.Column("task_key", sa.String(120), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("current_step", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="dormant"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("relevant_memory_refs_json", sa.Text(), nullable=False),
        sa.Column("selected_modules_json", sa.Text(), nullable=False),
        sa.Column("pending_commitments_json", sa.Text(), nullable=False),
        sa.Column("checkpoint_json", sa.Text(), nullable=True),
        sa.Column("resume_triggers_json", sa.Text(), nullable=False),
        sa.Column("affective_state_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column("last_activated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("task_key", name="uq_cognitive_task_contexts_task_key"),
        sa.CheckConstraint(
            "status IN ('active','paused','waiting','dormant','completed','cancelled')",
            name="ck_cognitive_task_contexts_status",
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 10",
            name="ck_cognitive_task_contexts_priority",
        ),
        sa.CheckConstraint(
            "created_by IN ('shree','rohit','system')",
            name="ck_cognitive_task_contexts_created_by",
        ),
        sa.CheckConstraint(
            "version_counter >= 1",
            name="ck_cognitive_task_contexts_version_counter",
        ),
    )
    op.create_index(
        "ix_cognitive_task_contexts_status_priority",
        "cognitive_task_contexts",
        ["status", "priority"],
    )


def downgrade() -> None:
    # Reverse dependency/creation order.  Audit history is intentionally lost
    # only when an operator explicitly runs this destructive downgrade.
    op.drop_index(
        "ix_cognitive_task_contexts_status_priority",
        table_name="cognitive_task_contexts",
    )
    op.drop_table("cognitive_task_contexts")
    op.drop_index(
        "ix_identity_reflection_logs_created",
        table_name="identity_reflection_logs",
    )
    op.drop_table("identity_reflection_logs")
    op.drop_index("ix_self_model_events_created", table_name="self_model_events")
    op.drop_table("self_model_events")
    op.drop_index("ix_module_routes_status", table_name="module_routes")
    op.drop_table("module_routes")
    op.drop_index(
        "ix_module_health_samples_key_created",
        table_name="module_health_samples",
    )
    op.drop_table("module_health_samples")
    op.drop_index(
        "ix_module_shadow_runs_key_created",
        table_name="module_shadow_runs",
    )
    op.drop_table("module_shadow_runs")
    op.drop_index(
        "ix_evaluation_runs_key_created",
        table_name="evaluation_runs",
    )
    op.drop_table("evaluation_runs")
    op.drop_index(
        "ix_surgery_sessions_key_status",
        table_name="surgery_sessions",
    )
    op.drop_table("surgery_sessions")
    op.drop_index(
        "ix_module_control_logs_key_created",
        table_name="module_control_logs",
    )
    op.drop_table("module_control_logs")
    op.drop_index(
        "ix_module_capability_envelopes_key_status",
        table_name="module_capability_envelopes",
    )
    op.drop_table("module_capability_envelopes")
    op.drop_index("ix_module_versions_key_status", table_name="module_versions")
    op.drop_index("ix_module_versions_module_key", table_name="module_versions")
    op.drop_table("module_versions")
    op.drop_index("ix_self_modules_module_type", table_name="self_modules")
    op.drop_index("ix_self_modules_status", table_name="self_modules")
    op.drop_table("self_modules")
    op.drop_index(
        "ix_self_module_proposals_status_created",
        table_name="self_module_proposals",
    )
    op.drop_index(
        "ix_self_module_proposals_module_key",
        table_name="self_module_proposals",
    )
    op.drop_table("self_module_proposals")
