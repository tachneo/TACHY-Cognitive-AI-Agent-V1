"""Action Engine — controlled automation (Phase 1E).

The brain's ideas become ACTIONS only through this gate. Principles:

- Whitelist: only registered actions exist; anything else is rejected.
- Risk tiers: low-risk actions (internal learning/goals/reflection) execute
  immediately with an audit trail; anything outward or state-changing goes
  through the persisted approval workflow and runs only after the guardian
  approves — from the API or simply by replying "approve <id>" on TODY.
- Payload-bound: an approval stores the exact JSON payload; execution
  re-validates it, so an approved action cannot be swapped for another.
- Every execution is audit-logged and remembered as a decision memory.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from app.memory import base_memory
from app.safety import approvals
from app.safety.audit_logger import log_event

BRAIN_ACTION = "brain_action"  # approvals.action name for gated actions


@dataclass(frozen=True)
class ActionSpec:
    name: str
    risk_tier: str  # low | medium | high
    description: str
    run: Callable[[dict], dict]


def _run_learn_topic(params: dict) -> dict:
    from app.brain import web_learning
    return web_learning.explore(str(params.get("topic") or "").strip() or None)


def _run_assign_homework(params: dict) -> dict:
    from app.brain import nurture_engine
    return nurture_engine.assign_homework(
        str(params["title"]), project=str(params.get("project", "PERSONAL")))


def _run_create_goal(params: dict) -> dict:
    from app.memory import goal_memory
    return goal_memory.create_goal(
        title=str(params["title"]),
        horizon=str(params.get("horizon", "short")),
        project=str(params.get("project", "GENERAL")))


def _run_daily_reflection(params: dict) -> dict:
    from app.brain.learning_engine import daily_reflection
    return daily_reflection()


def _run_consolidate(params: dict) -> dict:
    from app.brain import inner_life
    return inner_life.consolidate()


def _run_send_tody_message(params: dict) -> dict:
    # Outward action: delegated to the payload-bound TODY send approval flow.
    from app.agents import tody_agent
    return tody_agent.request_send(int(params["conversation_id"]),
                                   str(params["body"]))


REGISTRY: dict[str, ActionSpec] = {
    spec.name: spec for spec in (
        ActionSpec("learn_topic", "low",
                   "Research a topic on the web and store the lesson",
                   _run_learn_topic),
        ActionSpec("assign_homework", "low",
                   "Add a homework/study item for the brain",
                   _run_assign_homework),
        ActionSpec("create_goal", "low",
                   "Create a goal in goal memory", _run_create_goal),
        ActionSpec("daily_reflection", "low",
                   "Run the daily reflection pass", _run_daily_reflection),
        ActionSpec("consolidate_memory", "medium",
                   "Run memory consolidation (archives stale memories)",
                   _run_consolidate),
        ActionSpec("send_tody_message", "high",
                   "Send a TODY message (double-gated: queues a payload-bound "
                   "send approval)", _run_send_tody_message),
    )
}


def registry() -> list[dict]:
    return [{"name": s.name, "risk_tier": s.risk_tier,
             "description": s.description} for s in REGISTRY.values()]


def propose(action: str, params: dict | None = None) -> dict:
    """Propose an action. Low risk executes now; others wait for approval."""
    params = params or {}
    spec = REGISTRY.get(action)
    if spec is None:
        log_event("action_rejected", detail=f"unknown action: {action}",
                  risk_tier="medium")
        return {"accepted": False, "reason": f"unknown action '{action}'"}
    if spec.risk_tier == "low":
        return _execute(spec, params, approval_id=None)
    payload = json.dumps({"action": action, "params": params},
                         sort_keys=True, separators=(",", ":"))
    appr = approvals.request_approval(BRAIN_ACTION, payload=payload)
    log_event("action_proposed",
              detail=f"action={action}; approval_id={appr['id']}",
              risk_tier=spec.risk_tier)
    return {"accepted": True, "executed": False, "approval": appr,
            "note": f"'{action}' waits for guardian approval "
                    f"(#{appr['id']})."}


def execute_approved(approval_id: int) -> dict:
    """Run a gated action after its approval was approved (payload-bound)."""
    row = approvals.get_approval(approval_id)
    if row is None:
        return {"executed": False, "reason": "approval not found"}
    if row["status"] != "approved":
        return {"executed": False, "reason": f"approval is {row['status']}"}
    if row["action"] != BRAIN_ACTION:
        return {"executed": False,
                "reason": f"approval #{approval_id} is a '{row['action']}' "
                          "approval, not a brain action"}
    try:
        payload = json.loads(row["payload"] or "{}")
    except ValueError:
        return {"executed": False, "reason": "corrupt payload"}
    spec = REGISTRY.get(str(payload.get("action")))
    if spec is None:
        return {"executed": False, "reason": "action no longer registered"}
    return _execute(spec, payload.get("params") or {}, approval_id=approval_id)


def _execute(spec: ActionSpec, params: dict, *, approval_id: int | None) -> dict:
    try:
        result = spec.run(params)
        ok = True
    except Exception as exc:  # noqa: BLE001 — action failures must be reported
        result = {"error": f"{type(exc).__name__}: {exc}"}
        ok = False
    log_event("action_executed",
              detail=(f"action={spec.name}; ok={ok}; "
                      f"approval_id={approval_id}"),
              risk_tier=spec.risk_tier)
    base_memory.add(
        memory_type="decision",
        title=f"Action {'done' if ok else 'FAILED'}: {spec.name}",
        content=f"params={params}\nresult={str(result)[:600]}",
        project="AUTOMATION", source_type="action",
        importance_score=6 if ok else 8,
    )
    return {"accepted": True, "executed": ok, "action": spec.name,
            "approval_id": approval_id, "result": result}
