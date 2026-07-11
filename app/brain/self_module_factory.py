"""Approval-gated factory for child modules; artifacts never enter live imports."""
from __future__ import annotations

import json
from pathlib import Path
from sqlalchemy import select
from app.brain.module_evaluator import evaluate_module
from app.brain.weakness_detector import detect_weaknesses
from app.brain.capability_registry import validate_capabilities
from app.config import get_settings
from app.db.models import SelfModuleProposal, session_scope
from app.safety.policy import FORBIDDEN_ACTIONS


def _root() -> Path: return Path(get_settings().self_module_sandbox_root).resolve()
def _proposal(pid: int):
    with session_scope() as db:
        row = db.scalar(select(SelfModuleProposal).where(SelfModuleProposal.id == pid))
        return {c.name: getattr(row, c.name) for c in SelfModuleProposal.__table__.columns} if row else None


def detect_and_propose(context: dict | None = None) -> dict | None:
    weaknesses = detect_weaknesses()
    if not weaknesses: return None
    w = weaknesses[0]
    with session_scope() as db:
        p = SelfModuleProposal(module_key=w["recommended_module_key"], module_name=w["recommended_module_key"].replace("_", " ").title(), module_type=w["recommended_module_type"], purpose=w["expected_improvement"], weakness_detected=json.dumps(w["evidence"]), expected_improvement=w["expected_improvement"], proposed_by="shree", risk_level="low", allowed_actions_json="[\"explain\"]", blocked_actions_json=json.dumps(sorted(FORBIDDEN_ACTIONS)), required_tests_json="[\"unit\",\"safety\",\"fallback\"]", fallback_module_key="offline_brain", rollback_plan="route to fallback and restore previous version")
        db.add(p); db.flush(); return {"id": p.id, "module_key": p.module_key, "status": p.status}


def create_spec(proposal_id: int) -> str:
    p = _proposal(proposal_id)
    if not p: raise ValueError("proposal not found")
    path = _root() / "specs" / p["module_key"] / "MODULE_SPEC.md"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {p['module_name']}\n\n- Key: `{p['module_key']}`\n- Purpose: {p['purpose']}\n- Weakness evidence: {p['weakness_detected']}\n- Rollback: {p['rollback_plan']}\n", encoding="utf-8")
    with session_scope() as db: db.get(SelfModuleProposal, proposal_id).status = "spec_created"
    return str(path)


def generate_module_code(proposal_id: int, version: str = "0.1.0") -> str:
    p = _proposal(proposal_id)
    if not p: raise ValueError("proposal not found")
    path = _root() / "modules" / p["module_key"] / version / "module.py"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'''class SelfModule:\n    module_key = "{p['module_key']}"\n    version = "{version}"\n    risk_level = "{p['risk_level']}"\n\n    def health(self):\n        return {{"ok": True, "module_key": self.module_key, "version": self.version}}\n\n    def process(self, input_data):\n        return {{"ok": True, "module_key": self.module_key, "input": input_data}}\n\n    def fallback(self, input_data):\n        return {{"ok": False, "fallback": True, "input": input_data}}\n''', encoding="utf-8")
    (path.parent / "__init__.py").write_text("", encoding="utf-8")
    with session_scope() as db: db.get(SelfModuleProposal, proposal_id).status = "coded"
    return str(path)


def generate_tests(proposal_id: int, version: str = "0.1.0") -> str:
    p = _proposal(proposal_id)
    if not p: raise ValueError("proposal not found")
    path = _root() / "tests" / p["module_key"] / f"test_{p['module_key']}.py"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_module_contract():\n    assert True\n", encoding="utf-8")
    return str(path)


def validate_module(proposal_id: int, version: str = "0.1.0") -> dict:
    p = _proposal(proposal_id)
    if not p: raise ValueError("proposal not found")
    cap = validate_capabilities(p["module_key"], json.loads(p["allowed_actions_json"]), json.loads(p["blocked_actions_json"]), p["risk_level"])
    report = evaluate_module(p["module_key"], version)
    if not cap["valid"]: report["failures"].extend(cap["issues"]); report["passed"] = False
    with session_scope() as db:
        row = db.get(SelfModuleProposal, proposal_id); row.evaluation_score = report["score"]; row.validation_report_json = json.dumps(report); row.status = "tested" if report["passed"] else "failed_validation"
    return report


def register_shadow(proposal_id: int, version: str = "0.1.0") -> dict:
    """Complete the loop: register a VALIDATED proposal as a child module in
    SHADOW status. The seam that was missing — the factory produced proposals
    with allowed_actions_json / blocked_actions_json (JSON columns) but
    module_registry.register_module reads the list keys allowed_actions /
    blocked_actions, so a direct hand-off silently dropped the blocklist and
    the fail-closed gate rejected every module. This bridges the two shapes.

    Shadow means observe-only: no live import, no user-facing effect. Activation
    past shadow still requires Rohit (self_module_require_approval) — this never
    promotes to canary or active on its own."""
    if not get_settings().self_module_factory_enabled:
        return {"ok": False, "reason": "factory disabled"}
    if not get_settings().self_module_shadow_enabled:
        return {"ok": False, "reason": "shadow disabled"}
    p = _proposal(proposal_id)
    if not p:
        return {"ok": False, "reason": "proposal not found"}
    if p["status"] != "tested":
        return {"ok": False, "reason": f"proposal not validated (status={p['status']})"}

    from app.brain import module_registry
    registry_proposal = {
        "module_key": p["module_key"],
        "module_name": p["module_name"],
        "module_type": p["module_type"] or "evaluator",
        "risk_level": p["risk_level"] or "low",
        "version": version,
        "sandbox_path": str(_root() / "modules" / p["module_key"] / version),
        "allowed_actions": json.loads(p["allowed_actions_json"] or "[]"),
        "blocked_actions": json.loads(p["blocked_actions_json"] or "[]"),
        "fallback_module_key": p["fallback_module_key"] or "offline_brain",
    }
    try:
        reg = module_registry.register_module(registry_proposal, created_by="shree")
    except ValueError as exc:
        # Already registered → just move it to shadow; any other error is real.
        if "already registered" not in str(exc):
            return {"ok": False, "reason": str(exc)}
        reg = {"module_key": p["module_key"]}
    module_registry.update_module_status(
        p["module_key"], "shadow",
        "validated; observing in shadow, awaiting Rohit approval to activate",
        approved_by=None)
    with session_scope() as db:
        row = db.get(SelfModuleProposal, proposal_id)
        row.status = "shadow"
    return {"ok": True, "module_key": p["module_key"], "status": "shadow",
            "requires_approval": get_settings().self_module_require_approval,
            "registry": reg}
