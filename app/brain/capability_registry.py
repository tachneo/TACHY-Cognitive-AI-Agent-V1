"""Parent Kernel capability boundary for child modules.

This module is deliberately deterministic and independent of an LLM. A child
module can request capabilities, but only the kernel can validate and persist
the resulting envelope.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

from app.safety.policy import FORBIDDEN_ACTIONS, HIGH_RISK_ACTIONS, classify

HIGH_RISK = set(HIGH_RISK_ACTIONS) | {"alter_user_permissions", "production_deploy"}
FORBIDDEN = set(FORBIDDEN_ACTIONS)
PROTECTED_PATHS = (
    "app/safety/", "app/brain/identity_core.py", "app/brain/cognitive_loop.py",
    "app/config.py", ".env", "deployment/", "systemd/", "migrations/",
    "approval_gate.py", "policy.py", "secrets/", "production/",
)
SELF_ESCALATION = {
    "change_allowed_actions", "change_blocked_actions", "disable_approval",
    "alter_approval_requirement", "self_permission_escalation",
}


def _matches_protected(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./").lower()
    return any(normalized == protected or normalized.startswith(protected)
               for protected in PROTECTED_PATHS)


def validate_capabilities(
    module_key: str,
    allowed_actions: list[str] | tuple[str, ...],
    blocked_actions: list[str] | tuple[str, ...],
    risk_level: str,
    *,
    filesystem_scope: list[str] | None = None,
    network_scope: list[str] | None = None,
    data_scope: list[str] | None = None,
) -> dict:
    """Validate a capability request; never silently widen a request."""
    allowed = {str(a).strip().lower() for a in allowed_actions}
    blocked = {str(a).strip().lower() for a in blocked_actions}
    issues: list[str] = []
    risk = str(risk_level).lower()
    if risk not in {"low", "medium", "high", "critical"}:
        issues.append("invalid risk level")
    missing_forbidden = FORBIDDEN - blocked
    if missing_forbidden:
        issues.append("blocked_actions must include forbidden actions")
    illegal = allowed & FORBIDDEN
    if illegal:
        issues.append(f"forbidden actions requested: {sorted(illegal)}")
    escalation = allowed & SELF_ESCALATION
    if escalation:
        issues.append(f"self-permission escalation requested: {sorted(escalation)}")
    if "access_secrets" in allowed or "disable_security" in allowed:
        issues.append("secret access and security disabling are never child capabilities")
    high = allowed & HIGH_RISK
    requires_approval = risk in {"medium", "high", "critical"} or bool(high)
    if high and risk == "low":
        issues.append("high-risk action requires a medium or higher risk envelope")
    for scope_name, scope in (("filesystem", filesystem_scope or []),
                              ("network", network_scope or []),
                              ("data", data_scope or [])):
        for item in scope:
            if scope_name == "filesystem" and (_matches_protected(item) or Path(item).is_absolute()):
                issues.append(f"filesystem scope outside sandbox/protected: {item}")
            if scope_name == "network" and str(item).strip() not in {"none", "approved_provider"}:
                issues.append(f"unapproved network scope: {item}")
    if any(a in allowed for a in {"run_shell_command", "subprocess", "os.system"}):
        issues.append("shell execution is not a child-module capability")
    if module_key in {"parent_brain", "core_kernel", "safety_policy", "approval_gate"}:
        issues.append("child modules cannot register as an authority module")
    return {
        "valid": not issues,
        "risk_level": risk,
        "issues": issues,
        "requires_approval": requires_approval,
        "allowed_actions": sorted(allowed),
        "blocked_actions": sorted(blocked | FORBIDDEN),
    }


def path_is_safe(path: str, sandbox_root: str) -> bool:
    """Return true only for a path contained by the configured sandbox."""
    root = Path(sandbox_root).resolve()
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return not _matches_protected(str(candidate))
