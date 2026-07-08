"""Attention System + Emotion-Aware Priority Engine.

Turns raw scores into a single priority so the brain spends attention where it
matters (production bug > LinkedIn hashtag).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


@dataclass
class Signals:
    """Per-input scores, each 0..10."""
    security_risk: int = 0
    money_impact: int = 0
    client_impact: int = 0
    urgency: int = 0
    guardian_interest: int = 0
    emotional_weight: int = 0


def _read_mood_valence() -> float:
    """The persistent mood baseline (valence -1..1). Reads the same file
    emotion_engine writes — WITHOUT importing emotion_engine, which would be a
    circular import (emotion_engine imports this module's Signals). 0.0 when the
    file is absent or unreadable, so the mood term is a no-op until the emotion
    engine has run at least once."""
    try:
        path = Path(get_settings().emotion_mood_path)
        if path.exists():
            return float(json.loads(path.read_text(encoding="utf-8"))
                         .get("valence", 0.0))
    except (ValueError, OSError):
        pass
    return 0.0


def priority_score(s: Signals, *, mood_valence: float | None = None) -> int:
    """Emotion-aware priority formula from the Cognitive Brain OS plan.

    priority = security_risk*3 + money_impact*2 + client_impact*2
               + urgency + guardian_interest + emotional_weight

    The persistent mood baseline is a small VIGILANCE COEFFICIENT on top: a
    negative baseline (stress/worry) raises attention slightly — an anxious
    mind is more alert to incoming signals; a positive one eases it. Bounded to
    ±2/-1 so mood can nudge routing but NEVER override a real security or
    urgency signal. This is the link that makes emotion originate from Shree's
    own lived experience and actually change what she attends to — not just
    flavor her reply tone. ``mood_valence`` defaults to the file baseline.
    """
    base = (
        s.security_risk * 3
        + s.money_impact * 2
        + s.client_impact * 2
        + s.urgency
        + s.guardian_interest
        + s.emotional_weight
    )
    if mood_valence is None:
        mood_valence = _read_mood_valence()
    if mood_valence <= -0.15:
        base += 2
    elif mood_valence >= 0.15:
        base -= 1
    return max(0, base)


def attention_band(score: int) -> str:
    """Coarse routing band for the cognitive loop."""
    if score >= 60:
        return "critical"
    if score >= 35:
        return "high"
    if score >= 15:
        return "normal"
    return "low"
