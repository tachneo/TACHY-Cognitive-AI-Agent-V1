"""Conservative weakness detection from persisted evidence only."""
from __future__ import annotations

import json
from sqlalchemy import select
from app.db.models import EvaluationRun, ModuleHealthSample, SelfModelEvent, session_scope

# A repair-queue fix_class → the kind of child module that would address it.
# This is the bridge that turns Shree's own noticing (the metacognitive repair
# queue) into weakness evidence the module factory can act on — the link that
# was missing, which is why the factory had nothing to propose.
_FIXCLASS_TO_MODULE = {
    "directive": ("speech", "reply_style_guard"),
    "memory":    ("memory", "memory_recall_guard"),
    "config":    ("tool", "config_tuning_guard"),
    "code":      ("reasoning", "logic_repair_guard"),
    "capability": ("agent", "capability_extender"),
    "unknown":   ("evaluator", "generic_quality_guard"),
}


def _from_repair_queue(limit: int) -> list[dict]:
    """Ready repair-queue signatures (already past their evidence-tier
    recurrence threshold) → weaknesses. Evidence-only: nothing here is
    fabricated; a row is 'ready' only because a real failure recurred."""
    out: list[dict] = []
    try:
        from app.brain import repair_queue
        ready = repair_queue.ready(limit=limit)
    except Exception:  # noqa: BLE001
        return out
    for r in ready:
        mtype, mkey = _FIXCLASS_TO_MODULE.get(
            r.get("fix_class", "unknown"), _FIXCLASS_TO_MODULE["unknown"])
        # severity from recurrence + evidence tier (tier 1 = guardian = strongest)
        severity = min(10, 3 + int(r.get("recurrence", 1))
                       + (2 if int(r.get("tier", 4)) <= 2 else 0))
        out.append({
            "weakness_key": r["signature"],
            "severity": severity,
            "evidence": [f"tier={r.get('tier')}", f"recurrence={r.get('recurrence')}",
                         (r.get("sample") or "")[:120]],
            "recommended_module_type": mtype,
            "recommended_module_key": f"{mkey}_{r['signature'].replace(':','_').replace('-','_')}"[:110],
            "expected_improvement": f"stop the recurring '{r['signature']}' failure",
        })
    return out


def detect_weaknesses(limit: int = 10) -> list[dict]:
    findings: list[dict] = []
    # Her own noticing first — the strongest, most actionable evidence.
    findings.extend(_from_repair_queue(limit))
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
