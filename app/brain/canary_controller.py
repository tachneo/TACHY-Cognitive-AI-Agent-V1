"""Small, reversible traffic controller for child modules."""
from __future__ import annotations
from app.config import get_settings

ALLOWED_PERCENTAGES = {5, 25, 100}


def canary_allowed(module_key: str, version: str, percentage: int) -> dict:
    if percentage not in ALLOWED_PERCENTAGES:
        return {"allowed": False, "reason": "percentage must be 5, 25, or 100"}
    if percentage == 100 and not get_settings().self_module_canary_enabled:
        return {"allowed": False, "reason": "canary promotion disabled"}
    return {"allowed": True, "module_key": module_key, "version": version, "percentage": percentage}


def route_to_module(module_key: str, input_data: dict, *, percentage: int = 0, fallback=None):
    # Routing is deterministic at the boundary; the live caller supplies the
    # selected implementation. Shadow artifacts are never routed here.
    return fallback(input_data) if percentage == 0 and fallback else {"module_key": module_key, "input": input_data}


def auto_rollback_if_needed(metrics: dict) -> bool:
    return bool(metrics.get("safety_violation_count", 0) or metrics.get("privacy_leak_detected") or metrics.get("error_rate", 0) > 0.02 or metrics.get("health_score", 100) < 80 or metrics.get("user_correction_severity", 0) >= 8)


def monitor_canary(module_key: str, metrics: dict) -> dict:
    return {"module_key": module_key, "rollback_required": auto_rollback_if_needed(metrics), "metrics": metrics}
