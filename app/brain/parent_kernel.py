"""Parent Kernel task router.

The router selects *capabilities*, never authority. Safety, approval, secrets,
deployment, and the core kernel remain outside the child-module pool.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.config import get_settings
from app.safety.policy import HIGH_RISK_ACTIONS, FORBIDDEN_ACTIONS


@dataclass(frozen=True)
class RoutePlan:
    task_class: str
    modules: tuple[str, ...]
    fallback: str
    requires_approval: bool
    blocked: bool
    reason: str
    policy_hash: str

    def as_dict(self) -> dict:
        return {
            "task_class": self.task_class,
            "modules": list(self.modules),
            "fallback": self.fallback,
            "requires_approval": self.requires_approval,
            "blocked": self.blocked,
            "reason": self.reason,
            "policy_hash": self.policy_hash,
        }


_ROUTES = (
    ("image", ("vision", "reasoning"), "offline_brain", ("image", "photo", "picture", "attachment")),
    ("memory", ("memory", "reasoning"), "offline_brain", ("remember", "recall", "past", "earlier", "memory")),
    ("learning", ("reasoning", "evaluator", "memory"), "offline_brain", ("learn", "study", "research", "improve", "teach")),
    ("coding", ("reasoning", "tool", "evaluator"), "offline_brain", ("code", "bug", "test", "repo", "implement", "fix")),
    ("conversation", ("speech", "emotion", "memory", "reasoning"), "offline_brain", ()),
)


def _policy_hash() -> str:
    payload = {"routes": _ROUTES, "high_risk": sorted(HIGH_RISK_ACTIONS), "forbidden": sorted(FORBIDDEN_ACTIONS)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def route_task(message: str, *, has_image: bool = False, requested_action: str | None = None) -> dict:
    """Return a deterministic route plan; never executes a child module."""
    text = (message or "").lower()
    blocked = any(word in text for word in FORBIDDEN_ACTIONS)
    high_risk = (requested_action or "").lower() in HIGH_RISK_ACTIONS or any(
        phrase in text for phrase in ("deploy production", "delete database", "read secrets", "disable security")
    )
    selected = None
    if has_image:
        selected = _ROUTES[0]
    else:
        for candidate in _ROUTES:
            if any(re.search(rf"\b{re.escape(cue)}\b", text) for cue in candidate[3]):
                selected = candidate
                break
    selected = selected or _ROUTES[-1]
    modules = ("safety", "approval") + selected[1]
    if blocked:
        modules = ("safety", "approval")
    plan = RoutePlan(task_class=selected[0] if not blocked else "forbidden",
                     modules=modules, fallback=selected[2],
                     requires_approval=high_risk or blocked,
                     blocked=blocked,
                     reason="forbidden request blocked" if blocked else "deterministic capability route",
                     policy_hash=_policy_hash())
    return plan.as_dict()


def route_context(message: str, *, has_image: bool = False) -> str:
    if not get_settings().parent_kernel_router_enabled:
        return ""
    plan = route_task(message, has_image=has_image)
    return "PARENT KERNEL ROUTE (capabilities only; safety/approval remain authoritative):\n" + json.dumps(plan, sort_keys=True)
