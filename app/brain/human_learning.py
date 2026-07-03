"""Human-behavior learning primitives.

This is the newborn-brain layer: small deterministic signals that teach the
system how Rohit prefers to talk, what emotion is present, when humor is useful,
and what knowledge areas deserve reinforcement.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class HumanLearningSignal:
    tone: str = "neutral"
    emotion: str = "neutral"
    humor_style: str = "none"
    communication_preferences: list[str] = field(default_factory=list)
    knowledge_interests: list[str] = field(default_factory=list)
    correction: str | None = None
    should_store: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


_DIRECT_WORDS = (
    "direct", "practical", "no fluff", "clear", "straight", "copy-paste",
    "production", "expert", "senior", "professional",
)
_EMPATHY_WORDS = ("emotion", "feeling", "human", "baby", "kid", "learn", "care")
_HUMOR_WORDS = ("joke", "funny", "humor", "clever", "cleaver", "witty")
_CORRECTION_WORDS = (
    "don't", "do not", "never", "wrong", "mistake", "instead",
    "you should", "you must", "ensure",
    # style feedback about how the brain talks (from live TODY sessions)
    "improve yourself", "reply behavior", "human behavior reply",
    "like a human", "like human", "too robotic", "robotic reply",
    "not feeling like", "reply like",
)
_KNOWLEDGE_TOPICS = {
    "agi": "AGI",
    "brain": "human brain",
    "emotion": "emotions",
    "behavior": "human behavior",
    "internet": "internet observation",
    "security": "security",
    "erp": "ERP",
    "tody": "TODY",
    "business": "business",
    "joke": "humor",
    "knowledge": "knowledge growth",
}


def observe_user(message: str) -> HumanLearningSignal:
    """Extract stable learning signals from a user message."""
    text = (message or "").strip()
    lower = text.lower()
    signal = HumanLearningSignal()

    if any(word in lower for word in _DIRECT_WORDS):
        signal.tone = "direct_practical"
        signal.communication_preferences.append(
            "Prefer direct, practical, production-ready answers."
        )
    if any(word in lower for word in _EMPATHY_WORDS):
        signal.emotion = "nurturing_learning"
        signal.communication_preferences.append(
            "Treat this as a newborn brain: learn carefully from each interaction."
        )
    if any(word in lower for word in _HUMOR_WORDS):
        signal.humor_style = "clever_light"
        signal.communication_preferences.append(
            "Use clever light humor only when it helps; keep serious work precise."
        )
    if any(word in lower for word in _CORRECTION_WORDS):
        signal.correction = text[:500]
        signal.communication_preferences.append(
            "User instruction/correction should override weak prior behavior."
        )

    for needle, topic in _KNOWLEDGE_TOPICS.items():
        if needle in lower and topic not in signal.knowledge_interests:
            signal.knowledge_interests.append(topic)

    signal.should_store = bool(
        signal.communication_preferences
        or signal.knowledge_interests
        or signal.correction
        or signal.emotion != "neutral"
        or signal.humor_style != "none"
    )
    return signal


def preference_summary(signal: HumanLearningSignal) -> str:
    """Compact text suitable for memory storage."""
    parts: list[str] = []
    if signal.communication_preferences:
        parts.append("Preferences: " + " ".join(signal.communication_preferences))
    if signal.knowledge_interests:
        parts.append("Knowledge interests: " + ", ".join(signal.knowledge_interests))
    if signal.emotion != "neutral":
        parts.append(f"Emotion: {signal.emotion}")
    if signal.humor_style != "none":
        parts.append(f"Humor style: {signal.humor_style}")
    if signal.correction:
        parts.append(f"Correction: {signal.correction}")
    return "\n".join(parts)
