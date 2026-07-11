"""Conservative weakness detection from persisted evidence only."""
from __future__ import annotations

import json
from sqlalchemy import select
from app.db.models import EvaluationRun, ModuleHealthSample, SelfModelEvent, session_scope


def detect_weaknesses(limit: int = 10) -> list[dict]:
    findings: list[dict] = []
    with session_scope() as db:
        for run in db.scalars(select(EvaluationRun).where(EvaluationRun.passed.is_(False)).order_by(EvaluationRun.created_at.desc()).limit(limit)).all():
            findings.append({"weakness_key": "evaluation_failure", "severity": 7,
                             "evidence": [run.eval_name, run.failures_json],
                             "recommended_module_type": "evaluator",
                             "recommended_module_key": "evaluation_guard",
                             "expected_improvement": "raise failing evaluation dimensions"})
        for sample in db.scalars(select(ModuleHealthSample).where(ModuleHealthSample.health_score < 80).order_by(ModuleHealthSample.created_at.desc()).limit(limit)).all():
            findings.append({"weakness_key": "poor_module_health", "severity": 8,
                             "evidence": [f"health_score={sample.health_score}", f"error_rate={sample.error_rate}"],
                             "recommended_module_type": "evaluator",
                             "recommended_module_key": "module_health_guard",
                             "expected_improvement": "reduce errors and trigger safer fallback"})
        for event in db.scalars(select(SelfModelEvent).order_by(SelfModelEvent.created_at.desc()).limit(limit)).all():
            if float(event.confidence) < 50:
                findings.append({"weakness_key": "weak_self_identity_consistency", "severity": 5,
                                 "evidence": [event.event, event.evidence],
                                 "recommended_module_type": "self_model",
                                 "recommended_module_key": "self_consistency_guard",
                                 "expected_improvement": "ground reflections in stronger evidence"})
    return findings[:limit]
