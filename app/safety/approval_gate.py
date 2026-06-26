"""Approval gate — enforces the risk tiers before any action runs."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.safety.policy import RiskTier, classify


@dataclass
class GateResult:
    allowed: bool
    tier: RiskTier
    requires_approval: bool
    reason: str


def evaluate(action: str) -> GateResult:
    """Decide whether `action` can proceed, warn, wait for approval, or is blocked."""
    settings = get_settings()
    tier = classify(action)

    if tier is RiskTier.FORBIDDEN:
        return GateResult(False, tier, False, "Action is forbidden by policy.")

    if tier is RiskTier.HIGH:
        needs = settings.safety_enforce and settings.high_risk_require_approval
        return GateResult(
            allowed=not needs,
            tier=tier,
            requires_approval=needs,
            reason="High-risk action requires the guardian's explicit approval."
            if needs else "High-risk action allowed (enforcement off).",
        )

    if tier is RiskTier.MEDIUM:
        return GateResult(True, tier, False, "Medium-risk: proceed with a warning.")

    return GateResult(True, tier, False, "Low-risk: auto-allowed.")
