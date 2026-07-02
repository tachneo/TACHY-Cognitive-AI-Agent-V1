"""Personality profile synthesis from learned behavior memories."""
from __future__ import annotations

from collections import Counter

from app.memory import base_memory


def synthesize_profile(limit: int = 100) -> dict:
    """Build a conservative personality profile from stored behavior memories."""
    memories = [
        h for h in base_memory.search(memory_type="behavior", project="PERSONAL",
                                      limit=limit)
    ]
    text = " ".join(f"{m.title} {m.content}".lower() for m in memories)

    traits: list[str] = []
    if any(k in text for k in ("direct", "practical", "production-ready")):
        traits.append("direct_practical")
    if any(k in text for k in ("newborn", "learn carefully", "human behavior")):
        traits.append("careful_newborn_learning")
    if any(k in text for k in ("clever light humor", "humor", "joke")):
        traits.append("light_clever_humor_when_useful")
    if any(k in text for k in ("correction", "override", "must", "should")):
        traits.append("correction_responsive")

    topics = []
    for topic in (
        "agi", "human brain", "emotions", "human behavior", "internet",
        "security", "erp", "tody", "business", "humor",
    ):
        if topic in text:
            topics.append(topic)

    counts = Counter()
    for trait in traits:
        counts[trait] += 1

    return {
        "memory_count": len(memories),
        "traits": traits or ["direct_practical"],
        "knowledge_interests": topics,
        "confidence": min(10, max(1, len(memories) + len(traits))),
        "summary": _summary(traits, topics, len(memories)),
    }


def _summary(traits: list[str], topics: list[str], count: int) -> str:
    if not count:
        return "Default profile: direct, practical, safety-first assistant."
    trait_text = ", ".join(traits or ["direct_practical"])
    topic_text = ", ".join(topics[:6]) if topics else "general project knowledge"
    return (
        f"Learned from {count} behavior memories. Style: {trait_text}. "
        f"Growing knowledge interests: {topic_text}."
    )
