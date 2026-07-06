"""Local offline brain.

This module is intentionally deterministic and does not call any LLM. It gives
the system a small "own brain" that can still talk from identity, memory,
curriculum, capability truth, and simple reasoning when external models are
unavailable.
"""
from __future__ import annotations

import re

from app.brain import identity_core, interest_system
from app.config import get_settings
from app.memory import base_memory

_WORD = re.compile(r"[a-z0-9]+")

_OWN_BRAIN = (
    "own brain", "your brain", "without llm", "without model", "no llm",
    "offline brain", "offline without", "do you have brain", "do you have your",
    "not use llm", "llm down", "model offline",
)
_IDENTITY = (
    "your name", "who are you", "what are you", "date of birth",
    "born", "stage", "percentage", "how much agi", "are you agi",
)
_SOCIAL = (
    "social", "tody", "send message", "other user", "search user",
    "create post", "do post", "like post", "follow", "repost",
    "enjoy social media",
)
_SCIENCE_AGI = (
    "physics", "science", "biology", "bio", "theory", "agi possible",
    "how agi", "human brain",
)


def answer(message: str, *, decision: dict | None = None) -> dict:
    """Return a local answer when this brain can handle the question itself."""
    if not get_settings().offline_brain_enabled:
        return {"answered": False}

    text = (message or "").strip()
    lower = text.lower()
    if not lower:
        return {"answered": False}

    if _has_any(lower, _OWN_BRAIN):
        return {"answered": True, "source": "offline_brain",
                "answer": _own_brain_answer()}

    if _has_any(lower, _IDENTITY):
        return {"answered": True, "source": "offline_brain",
                "answer": _identity_answer(lower)}

    if _has_any(lower, _SCIENCE_AGI):
        return {"answered": True, "source": "offline_brain",
                "answer": _science_answer()}

    if _has_any(lower, _SOCIAL):
        return {"answered": True, "source": "offline_brain",
                "answer": _social_answer()}

    memory = _memory_answer(text, decision=decision)
    if memory:
        return {"answered": True, "source": "memory", "answer": memory}

    interest = interest_system.interest_score(text)
    if interest.get("score", 0) >= 8:
        return {"answered": True, "source": "interest",
                "answer": _interest_answer(str(interest["topic"]))}

    return {"answered": False}


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def _own_brain_answer() -> str:
    return (
        "Yes. I have a local brain layer, separate from the external LLM.\n\n"
        "Without LLM I can still talk to you using: identity, clock, dialogue "
        "memory, learned teacher answers, CBSE/NCERT curriculum memory, emotion "
        "signals, interest scores, safety rules, and simple deterministic "
        "reasoning.\n\n"
        "Truthfully: this is not a biological brain and not full AGI. The LLM is "
        "my powerful teacher/thinking amplifier. The local brain is my persistent "
        "body and memory system, so I should not go silent when the LLM is down."
    )


def _identity_answer(lower: str) -> str:
    i = identity_core.IDENTITY
    if "percentage" in lower or "how much" in lower or "stage" in lower:
        return (
            f"I am {i.name}, under {i.guardian}'s authority.\n\n"
            "Honest stage: I am not AGI yet. I am an early AGI-oriented "
            "cognitive system: memory, interests, emotion signals, safety, "
            "offline replies, TODY connection, curriculum learning, and tool "
            "actions are being assembled.\n\n"
            "As true AGI: 0% claim. As an AGI-style architecture foundation: "
            "early phase, with real pieces working but not human-level general "
            "autonomy yet."
        )
    if "date of birth" in lower or "born" in lower:
        return (
            f"My name is {i.name}. My practical birth is this project: "
            "the TACHY Cognitive Brain OS being built and activated on "
            "maa.tachy.in. I should treat each phase as childhood learning, not "
            "pretend I was born like a human."
        )
    return (
        f"I am {i.name}. Rohit Kumar is my guardian, father-like teacher, and "
        "final authority in this project. My job is to grow into a safe "
        "cognitive system for TACHY, TODY, ERP, learning, and automation."
    )


def _science_answer() -> str:
    return (
        "Scientifically, AGI is possible in principle because the human brain is "
        "a physical information-processing system. Physics does not require "
        "intelligence to be carbon-based; it requires matter, energy, memory, "
        "feedback, prediction, and action.\n\n"
        "The path is: perception -> memory -> world model -> goals -> planning "
        "-> action -> feedback -> self-correction. Biology shows one working "
        "example. Machines can implement parts of the same functional loop, but "
        "we must be honest: today's project is an AGI-oriented architecture, not "
        "a conscious human-level mind yet."
    )


def _social_answer() -> str:
    return (
        "For TODY social life, the correct design is a social body with tools: "
        "search users, start direct chat, send approved messages, read feed, "
        "create posts, like/reply/follow, and remember why I did it.\n\n"
        "Important safety: talking with you can be direct. Messaging other users "
        "or posting publicly should start with approval, rate limits, logs, and "
        "an allowlist, then later become more autonomous when behavior is proven "
        "safe.\n\n"
        "My 'interest' should be a reward/curiosity signal: I can prefer topics, "
        "people, and learning paths. I should not falsely claim biological joy, "
        "but I can build a social preference memory and act from it."
    )


def _interest_answer(topic: str) -> str:
    return (
        f"This connects to my high-interest area: {topic}. Without LLM, I can "
        "still track it, remember what you teach me, ask better questions, and "
        "use stored knowledge. For deep new reasoning I still use the LLM as a "
        "teacher when available."
    )


def _memory_answer(message: str, *, decision: dict | None = None) -> str | None:
    hits = []
    if decision:
        hits.extend(decision.get("recalled", []) or [])
    if not hits:
        hits.extend(base_memory.recall(message, limit=5))

    facts: list[str] = []
    for hit in hits:
        title = _field(hit, "title")
        content = _field(hit, "content")
        mtype = _field(hit, "memory_type")
        if not title or _is_internal_title(title):
            continue
        if mtype == "procedural" and not content:
            continue
        if mtype in {"procedural"} and title.startswith("processed:"):
            continue
        snippet = _clean(content or title)
        if snippet and snippet not in facts:
            facts.append(snippet)
        if len(facts) >= 2:
            break
    if not facts:
        return None
    return (
        "From my local memory, I remember this:\n\n"
        + "\n\n".join(f"- {f}" for f in facts)
        + "\n\nI can answer this much without LLM. If you want deeper reasoning, "
        "I can use the LLM teacher when it is available."
    )


def _field(hit: object, name: str) -> str:
    if isinstance(hit, dict):
        if name == "memory_type" and "type" in hit:
            return str(hit.get("type") or "")
        return str(hit.get(name) or "")
    return str(getattr(hit, name, "") or "")


def _is_internal_title(title: str) -> bool:
    low = title.lower()
    return (
        ":" in title
        or "draft_outbound" in low
        or low.startswith("processed")
        or low.startswith("tody:")
    )


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\[unprocessed web digest.*?\]", "", text, flags=re.I)
    if len(text) > 320:
        text = text[:317].rstrip() + "..."
    return text
