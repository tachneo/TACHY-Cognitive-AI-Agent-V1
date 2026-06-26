"""Interest System — Rohit's long-term interest profile.

Higher interest → more attention/guardian_interest weight. Scores start from the
plan's seed profile and can be reinforced over time by the learning engine.
"""
from __future__ import annotations

# Seed interest scores (0..10) from the Cognitive Brain OS plan.
SEED_INTERESTS: dict[str, int] = {
    "agi": 10,
    "ahi": 10,
    "tachy school erp": 9,
    "tody": 9,
    "security": 9,
    "hacking prevention": 9,
    "php": 7,
    "mysql": 7,
    "python": 7,
    "android": 7,
    "erp": 8,
    "crm": 7,
    "ai automation": 8,
    "business growth": 8,
    "client proposal": 8,
    "indian market": 7,
    "bhagavad gita": 8,
}


def interest_score(text: str) -> dict:
    """Best-matching interest topic and its score for the given text."""
    t = (text or "").lower()
    best_topic, best = None, 0
    for topic, score in SEED_INTERESTS.items():
        if topic in t and score > best:
            best_topic, best = topic, score
    return {"topic": best_topic, "score": best}
