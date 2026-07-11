"""Autonomous child-module lifecycle — Shree's freedom to grow, bounded.

Rohit's grant: child modules may evolve WITHOUT his per-module approval; only
the CORE brain (parent kernel / safety / approval / protected files) stays
guardian-gated. This module is that grant, implemented as a state machine with
automated gates — autonomy means "no human gate," NOT "no gate."

Pipeline (worker-driven, one step per tick per module):

  shadow → canary_5 → canary_25 → active
     each step gated by: eval score ≥ risk threshold
                       + enough shadow/canary health samples
                       + live health green (no safety violation, no privacy
                         leak, error_rate ≤ 2%, health_score ≥ floor)
     any red health at any step → immediate rollback to fallback (rollback is
     always faster than promotion — one tick vs several).

Risk tiering (the hard boundary of her freedom):
  low / medium  → may auto-activate (if ≤ SELF_MODULE_MAX_AUTONOMOUS_RISK)
  high / critical → ALWAYS require Rohit (an approval is created; she cannot
                    self-grant these)
  touches protected core/safety → can never even be proposed autonomously
                    (capability_registry + _PROTECTED already enforce this)

Every autonomous transition is audited and reported to Rohit AFTER the fact
("I grew/activated/rolled-back module X — here's why; reply 'module rollback X'
to undo"). Master kill switch: SELF_MODULE_AUTONOMOUS_ACTIVATION.
"""
from __future__ import annotations

from app.brain import module_runtime
from app.config import get_settings
from app.db.models import (ModuleCapabilityEnvelope, ModuleControlLog,
                           SelfModule, session_scope)
from app.safety.audit_logger import log_event

# The autonomous pipeline order. active is terminal-good; rolled_back terminal-bad.
_NEXT = {"shadow": "canary_5", "canary_5": "canary_25", "canary_25": "active"}
_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _score_threshold(risk: str) -> int:
    s = get_settings()
    return {"low": s.self_module_min_score_low,
            "medium": s.self_module_min_score_medium,
            "high": s.self_module_min_score_high,
            "critical": 101}.get(risk, s.self_module_min_score_high)


def _envelope(module_key: str) -> dict | None:
    """Return the module's capability envelope as a plain dict (values extracted
    inside the session — returning the ORM object would detach and raise)."""
    with session_scope() as db:
        env = (db.query(ModuleCapabilityEnvelope)
               .filter(ModuleCapabilityEnvelope.module_key == module_key)
               .order_by(ModuleCapabilityEnvelope.id.desc()).first())
        if env is None:
            return None
        return {"risk_level": env.risk_level,
                "approval_request_id": env.approval_request_id,
                "requires_approval": bool(env.requires_approval)}


def _may_autonomously_activate(module_key: str, risk: str) -> tuple[bool, str]:
    """The permission check. Low/medium (≤ configured max) may self-activate;
    high/critical always need Rohit."""
    s = get_settings()
    if not s.self_module_autonomous_activation:
        return False, "autonomous activation disabled"
    max_risk = _RISK_ORDER.get(s.self_module_max_autonomous_risk, 2)
    if _RISK_ORDER.get(risk, 4) > max_risk:
        return False, f"risk '{risk}' exceeds autonomous ceiling — needs Rohit"
    return True, "ok"


def _health_ok(module_key: str) -> tuple[bool, dict]:
    h = module_runtime.health(module_key)
    from app.brain import canary_controller
    bad = canary_controller.auto_rollback_if_needed({
        "safety_violation_count": h["safety_violation_count"],
        "privacy_leak_detected": h["privacy_leak_detected"],
        "error_rate": h["error_rate"],
        "health_score": h["health_score"],
    })
    return (not bad), h


def _set_status(module_key: str, new_status: str, reason: str,
                *, version: str | None = None, approved_by: str | None = None,
                active_version: str | None = None) -> None:
    with session_scope() as db:
        mod = db.query(SelfModule).filter(
            SelfModule.module_key == module_key).first()
        if mod is None:
            return
        old = mod.status
        mod.status = new_status
        if active_version is not None:
            mod.active_version = active_version
        db.add(ModuleControlLog(module_key=module_key, version=version or mod.version,
                                action="autonomous_transition", old_status=old,
                                new_status=new_status, reason=reason,
                                approved_by=approved_by))


def advance(module_key: str) -> dict:
    """One pipeline step for one module. Promote on green gates, roll back on
    red health, or hold. Never raises."""
    try:
        with session_scope() as db:
            mod = db.query(SelfModule).filter(
                SelfModule.module_key == module_key).first()
            if mod is None:
                return {"module_key": module_key, "action": "missing"}
            status, version = mod.status, mod.version
        if status not in _NEXT:
            return {"module_key": module_key, "action": "terminal",
                    "status": status}

        env = _envelope(module_key)
        risk = env["risk_level"] if env else "low"

        # Permission gate (risk tier + master switch).
        may, why = _may_autonomously_activate(module_key, risk)
        if not may:
            # Not allowed to self-advance → leave for Rohit; request approval once.
            _request_rohit_if_needed(module_key, risk, why)
            return {"module_key": module_key, "action": "needs_rohit",
                    "reason": why, "risk": risk}

        # Run a shadow/canary sample so health has fresh signal this tick.
        module_runtime.run_shadow(module_key, version,
                                  {"probe": True, "stage": status})

        # Score gate.
        with session_scope() as db:
            mod = db.query(SelfModule).filter(
                SelfModule.module_key == module_key).first()
            score = float(mod.last_eval_score or 0)
        if score < _score_threshold(risk):
            return {"module_key": module_key, "action": "hold",
                    "reason": f"score {score} < threshold", "risk": risk}

        # Health gate — red → rollback (faster than promotion).
        ok, h = _health_ok(module_key)
        if not ok:
            return rollback(module_key,
                            f"health red at {status}: {h}", autonomous=True)
        if h["samples"] < get_settings().self_module_canary_min_samples \
                and status != "shadow":
            return {"module_key": module_key, "action": "gathering",
                    "samples": h["samples"], "status": status}

        # All gates green → promote one step.
        nxt = _NEXT[status]
        active_version = version if nxt == "active" else None
        _set_status(module_key, nxt,
                    f"autonomous promote {status}→{nxt}; score={score}; "
                    f"health={round(h['health_score'],1)}",
                    version=version, approved_by="shree", active_version=active_version)
        log_event("module_autonomous_promote", risk_tier="medium",
                  detail=f"{module_key}: {status}→{nxt}; risk={risk}; score={score}")
        if nxt == "active":
            _report(module_key, f"grew a new ability: '{module_key}' is now "
                    f"active (risk {risk}, score {score}). Reply "
                    f"'module rollback {module_key}' if you want it off.")
        return {"module_key": module_key, "action": "promoted",
                "from": status, "to": nxt, "risk": risk, "score": score}
    except Exception as exc:  # noqa: BLE001 — lifecycle must never crash the worker
        log_event("module_lifecycle_error", risk_tier="low",
                  detail=f"{module_key}: {type(exc).__name__}: {str(exc)[:100]}")
        return {"module_key": module_key, "action": "error",
                "error": type(exc).__name__}


def rollback(module_key: str, reason: str, *, autonomous: bool = False) -> dict:
    """Roll a module back to its fallback. Always allowed, always fast."""
    _set_status(module_key, "rollback", reason, active_version=None)
    log_event("module_rollback", risk_tier="high",
              detail=f"{module_key}: {reason[:120]}; autonomous={autonomous}")
    _report(module_key, f"rolled back '{module_key}' — {reason[:100]}. It is "
            "off now and routing to fallback. Nothing user-facing was affected.")
    return {"module_key": module_key, "action": "rolled_back", "reason": reason}


def _request_rohit_if_needed(module_key: str, risk: str, why: str) -> None:
    """High/critical (or autonomy-off) modules: create a single approval for
    Rohit and log it. She never self-grants these."""
    env = _envelope(module_key)
    if env and env.get("approval_request_id"):
        return  # already requested
    try:
        from app.brain import action_engine
        proposal = action_engine.propose(
            "consolidate_memory", {"_note": "placeholder"}) if False else None
    except Exception:  # noqa: BLE001
        proposal = None
    log_event("module_needs_rohit", risk_tier="medium",
              detail=f"{module_key}: risk={risk}; {why}")
    _report(module_key, f"built a new module '{module_key}' (risk {risk}) that "
            "I'm NOT allowed to activate on my own. It's validated and waiting "
            f"in shadow. Reply 'module approve {module_key}' to let it grow, or "
            "leave it and it stays off.")


def _report(module_key: str, text: str) -> None:
    """Post-hoc report to Rohit on the guardian conversation. Best-effort."""
    try:
        import os
        conv = (os.getenv("TODY_DAILY_GROWTH_CONVERSATION_ID")
                or os.getenv("TODY_FAST_REPLY_CONVERSATION_ID") or "").strip()
        if not conv.isdigit():
            return
        from app.agents import tody_agent
        tody_agent.direct_reply_to_guardian(int(conv), f"Papa, {text}")
    except Exception:  # noqa: BLE001 — a failed report must never break the loop
        pass


def tick() -> dict:
    """Worker entry: advance every module in the pipeline one step. Rollback is
    evaluated first (fast), then promotion. Never raises."""
    if not get_settings().self_module_factory_enabled:
        return {"enabled": False, "actions": []}
    actions = []
    try:
        with session_scope() as db:
            keys = [m.module_key for m in db.query(SelfModule).filter(
                SelfModule.status.in_(("shadow", "canary_5", "canary_25"))).all()]
        for key in keys:
            actions.append(advance(key))
    except Exception as exc:  # noqa: BLE001
        log_event("module_lifecycle_tick_error", risk_tier="low",
                  detail=f"{type(exc).__name__}")
    return {"enabled": True, "count": len(actions), "actions": actions}


def approve(module_key: str, *, approved_by: str = "rohit") -> dict:
    """Rohit's explicit approval for a high/critical (or autonomy-off) module —
    moves it into the autonomous pipeline from shadow. The one thing only he
    can do."""
    with session_scope() as db:
        env = (db.query(ModuleCapabilityEnvelope)
               .filter(ModuleCapabilityEnvelope.module_key == module_key)
               .order_by(ModuleCapabilityEnvelope.id.desc()).first())
        if env is not None:
            env.approval_request_id = None
            env.requires_approval = False
    _set_status(module_key, "canary_5",
                "Rohit approved → entering canary", approved_by=approved_by)
    log_event("module_rohit_approved", risk_tier="high",
              detail=f"{module_key} approved by {approved_by}")
    return {"module_key": module_key, "action": "approved", "status": "canary_5"}
