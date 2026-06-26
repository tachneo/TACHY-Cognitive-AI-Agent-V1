"""Decision Engine — the reasoning pipeline.

understand → recall memory → identify project/risk → generate options →
simulate → choose safest useful action → decide approval → explain.
Returns a structured trace so the answer is transparent and auditable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.brain.simulation_engine import simulate
from app.memory.base_memory import recall
from app.safety.approval_gate import evaluate as gate_evaluate


# Crude project router; replaced by project_memory matching in a later phase.
def detect_project(text: str) -> str:
    t = (text or "").lower()
    if "tody" in t:
        return "TODY"
    if "erp" in t or "school" in t or "fees" in t or "report card" in t:
        return "TACHY_SCHOOL_ERP"
    if "client" in t or "proposal" in t or "price" in t:
        return "ERP_CRM_AI"
    return "GENERAL"


# Map intent keywords to a safety-policy action name (see safety/policy.py).
def infer_action(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("deploy", "release to prod", "go live")):
        return "production_deploy"
    if any(k in t for k in ("delete", "drop table", "remove file")):
        return "delete_files"
    if any(k in t for k in ("migrate", "alter table", "update database", "modify db")):
        return "db_modify"
    if any(k in t for k in ("send email", "send message", "notify client")):
        return "send_email"
    if "review" in t and ("code" in t or "php" in t or "file" in t):
        return "review_code"
    return "explain"


@dataclass
class Decision:
    intent: str
    project: str
    action: str
    risk_tier: str
    requires_approval: bool
    options: list[str]
    chosen: str
    reason: str
    simulation: dict
    recalled: list[dict]


def decide(text: str) -> Decision:
    project = detect_project(text)
    action = infer_action(text)
    gate = gate_evaluate(action)

    hits = recall(text, limit=5)
    recalled = [{"id": h.id, "type": h.memory_type, "title": h.title,
                 "score": h.score} for h in hits]

    sim = simulate(action)

    options = [
        "Answer/explain only (safe).",
        "Draft a concrete plan or code suggestion for approval.",
    ]
    if gate.requires_approval:
        options.append("Request guardian approval, then execute.")

    if gate.tier.value == "forbidden":
        chosen = "Refuse — action is forbidden by policy."
    elif gate.requires_approval:
        chosen = "Prepare the work and request Rohit's approval before executing."
    else:
        chosen = "Proceed with the safest useful action and explain the reasoning."

    return Decision(
        intent=text.strip()[:200],
        project=project,
        action=action,
        risk_tier=gate.tier.value,
        requires_approval=gate.requires_approval,
        options=options,
        chosen=chosen,
        reason=gate.reason,
        simulation=sim.as_dict(),
        recalled=recalled,
    )


def as_dict(d: Decision) -> dict:
    return asdict(d)
