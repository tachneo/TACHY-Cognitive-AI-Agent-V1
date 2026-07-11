"""Phase 1 control-plane persistence contracts.

These tests intentionally exercise SQLAlchemy metadata and SQLite enforcement.
The production migration is covered separately, while this suite protects the
portable contracts used by local development and CI.
"""
from __future__ import annotations

from collections.abc import Iterable

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Base, IdentityReflectionLog, ModuleRoute, ModuleVersion, SelfModule,
)


NEW_TABLES = {
    "self_module_proposals",
    "self_modules",
    "module_versions",
    "module_capability_envelopes",
    "module_control_logs",
    "surgery_sessions",
    "evaluation_runs",
    "module_shadow_runs",
    "module_health_samples",
    "module_routes",
    "self_model_events",
    "identity_reflection_logs",
    "cognitive_task_contexts",
}


def _column_names(columns: Iterable[object]) -> tuple[str, ...]:
    return tuple(column.name for column in columns)


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    unique_sets = {
        _column_names(constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    unique_sets.update(
        (column.name,) for column in table.columns if column.unique
    )
    return unique_sets


def _foreign_key_targets(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {foreign_key.target_fullname for foreign_key in table.foreign_keys}


def _check_sql(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return " ".join(
        str(constraint.sqltext).lower()
        for constraint in table.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    )


def test_metadata_contains_all_phase1_control_plane_tables():
    assert NEW_TABLES <= set(Base.metadata.tables)


def test_create_all_builds_all_phase1_tables_on_sqlite():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert NEW_TABLES <= set(inspect(engine).get_table_names())


def test_critical_uniqueness_contracts_are_declared():
    assert ("module_key",) in _unique_column_sets("self_modules")
    assert ("module_key", "version") in _unique_column_sets("module_versions")
    assert ("module_key",) in _unique_column_sets("module_routes")


def test_module_children_reference_their_parent_records():
    version_targets = _foreign_key_targets("module_versions")
    assert "self_modules.module_key" in version_targets

    for table_name in (
        "module_capability_envelopes",
        "module_control_logs",
        "module_shadow_runs",
        "module_health_samples",
        "module_routes",
    ):
        targets = _foreign_key_targets(table_name)
        assert any(target.startswith("self_modules.") for target in targets), table_name


def test_lifecycle_and_bounded_values_have_database_checks():
    assert "risk_level" in _check_sql("self_module_proposals")
    assert "status" in _check_sql("self_module_proposals")
    assert "status" in _check_sql("self_modules")
    assert "status" in _check_sql("module_versions")
    assert "status" in _check_sql("surgery_sessions")
    assert "status" in _check_sql("cognitive_task_contexts")

    combined_checks = " ".join(
        _check_sql(table_name)
        for table_name in (
            "self_module_proposals",
            "module_versions",
            "evaluation_runs",
            "module_shadow_runs",
            "module_health_samples",
            "module_routes",
            "identity_reflection_logs",
            "cognitive_task_contexts",
        )
    )
    assert "score" in combined_checks
    assert "percentage" in _check_sql("module_routes")
    assert "priority" in _check_sql("cognitive_task_contexts")
    assert "version_counter" in _check_sql("cognitive_task_contexts")


def test_capability_policy_has_auditable_validity_fields():
    columns = Base.metadata.tables["module_capability_envelopes"].columns
    assert {"policy_hash", "status", "expires_at"} <= set(columns.keys())


def test_duplicate_module_and_version_are_rejected():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        module = SelfModule(
            module_key="memory_ranker", module_name="Memory Ranker",
            module_type="memory", sandbox_path="/tmp/memory_ranker",
            allowed_actions_json="[]", blocked_actions_json="[]",
            created_by="system",
        )
        session.add(module)
        session.commit()

        session.add(SelfModule(
            module_key="memory_ranker", module_name="Duplicate",
            module_type="memory", sandbox_path="/tmp/duplicate",
            allowed_actions_json="[]", blocked_actions_json="[]",
            created_by="system",
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add_all([
            ModuleVersion(
                module_key="memory_ranker", version="1.0.0", code_hash="c1",
                artifact_hash="a1", spec_path="s", sandbox_path="b",
                test_path="t",
            ),
            ModuleVersion(
                module_key="memory_ranker", version="1.0.0", code_hash="c2",
                artifact_hash="a2", spec_path="s2", sandbox_path="b2",
                test_path="t2",
            ),
        ])
        with pytest.raises(IntegrityError):
            session.commit()


def test_bounded_state_values_are_database_enforced():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SelfModule(
            module_key="bad_status", module_name="Bad", module_type="memory",
            status="not_a_lifecycle_state", sandbox_path="/tmp/bad",
            allowed_actions_json="[]", blocked_actions_json="[]",
            created_by="system",
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(IdentityReflectionLog(
            question="q", answer="a", self_state_json="{}",
            confidence=101, consistency_passed=False,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(ModuleRoute(
            module_key="missing", version="1.0.0", percentage=10,
            policy_snapshot_json="{}", policy_snapshot_hash="h",
            updated_by="system",
        ))
        with pytest.raises(IntegrityError):
            session.commit()
