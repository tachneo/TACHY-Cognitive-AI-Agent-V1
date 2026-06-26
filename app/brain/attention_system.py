"""Attention System + Emotion-Aware Priority Engine.

Turns raw scores into a single priority so the brain spends attention where it
matters (production bug > LinkedIn hashtag).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Signals:
    """Per-input scores, each 0..10."""
    security_risk: int = 0
    money_impact: int = 0
    client_impact: int = 0
    urgency: int = 0
    guardian_interest: int = 0
    emotional_weight: int = 0


def priority_score(s: Signals) -> int:
    """Emotion-aware priority formula from the Cognitive Brain OS plan.

    priority = security_risk*3 + money_impact*2 + client_impact*2
               + urgency + guardian_interest + emotional_weight
    """
    return (
        s.security_risk * 3
        + s.money_impact * 2
        + s.client_impact * 2
        + s.urgency
        + s.guardian_interest
        + s.emotional_weight
    )


def attention_band(score: int) -> str:
    """Coarse routing band for the cognitive loop."""
    if score >= 60:
        return "critical"
    if score >= 35:
        return "high"
    if score >= 15:
        return "normal"
    return "low"
