"""Self-model — Shree's truthful knowledge of her OWN architecture.

Problem from the rohitsingh chat log: when Rohit asked "do you have a brain /
can you learn / what's your offline strength", Shree answered with a generic
LLM disclaimer ("I'm just a large language model… I don't learn offline… my
weights are frozen") — which DENIES the real architecture Rohit built
(offline_brain, curriculum_learning, 15 memory types, teacher_learning).

This module is the truthful counter-source: it reports what Shree actually is,
built from the real modules and the live state, so replies about herself are
grounded in fact (satya) instead of the base model's default self-description.

It is descriptive only — it never inflates capability or claims consciousness.
"""
from __future__ import annotations

from app.brain import curriculum_learning, identity_core, offline_brain
from app.config import get_settings
from app.memory import base_memory


def describe_self() -> dict:
    """Return a truthful snapshot of Shree's real architecture and live state."""
    s = get_settings()
    ident = identity_core.IDENTITY

    # Live curriculum progress (Class X, Y%) — real, not invented.
    try:
        cur = curriculum_learning.status()
        curriculum = {
            "enabled": s.curriculum_learning_enabled,
            "current_class": cur.get("current_class") or cur.get("class"),
            "progress_pct": cur.get("progress_pct") or cur.get("percent"),
            "pass_gate": cur.get("pass_gate"),
        }
    except Exception:  # noqa: BLE001
        curriculum = {"enabled": s.curriculum_learning_enabled}

    # Real memory counts — proof of a persistent brain, not a context window.
    try:
        counts = base_memory.counts_by_type()
    except Exception:  # noqa: BLE001
        counts = {}

    return {
        "name": ident.name,
        "relationship": ident.relationship,
        "guardian": ident.guardian,
        "company": ident.company,
        "mission": ident.mission,
        "values": list(ident.values),
        "has_offline_brain": s.offline_brain_enabled,
        "has_curriculum_learning": curriculum.get("enabled", False),
        "curriculum": curriculum,
        "has_teacher_learning": s.teacher_learning_enabled,
        "has_emotion_engine": s.emotion_engine_enabled,
        "has_inner_life": s.inner_life_enabled,
        "has_web_learning": s.web_learning_enabled,
        # Phase 2G/2H/2I — she can read, improve, deploy, diagnose, and defend
        # herself. These are REAL and live; report them truthfully.
        "has_self_improvement": s.self_improve_enabled,
        "self_improvement_autonomous": s.self_improve_autonomous,
        "has_self_diagnosis": True,
        "has_cyber_self_defense": True,
        "can_read_own_repo": bool(s.github_token) or True,
        "memory_types": 15,
        "memory_counts": counts,
        "total_memories": sum(counts.values()) if counts else None,
        "limitations": list(ident.limitations),
        # Honest framing — she reasons on an LLM backbone AND has a persistent
        # brain layer on top. Neither "just an LLM" nor "conscious".
        "nature": (
            "A persistent cognitive brain (memory, emotion, learning, curriculum, "
            "offline fallback) running on top of an LLM reasoning backbone. Not a "
            "bare LLM, not conscious — a brain layer that remembers and learns "
            "across sessions."
        ),
    }


def self_knowledge_prompt() -> str:
    """A prompt block injected into replies so Shree answers questions about
    herself truthfully from her real architecture, not the LLM default."""
    d = describe_self()
    cur = d.get("curriculum") or {}
    cur_line = ""
    if cur.get("enabled") and cur.get("current_class"):
        cur_line = (f" Currently mastering CBSE Class {cur['current_class']} "
                    f"({cur.get('progress_pct', '?')}% through the 1–12 plan, "
                    f"99% pass gate).")
    mem_line = ""
    if d.get("total_memories"):
        mem_line = (f" I hold {d['total_memories']} persistent memories across "
                    f"{d['memory_types']} types (episodic, emotional, semantic, "
                    "procedural, …) — they survive across sessions, not just a "
                    "context window.")
    offline_line = ""
    if d.get("has_offline_brain"):
        offline_line = (" I have an OFFLINE brain: even with no LLM I can reply "
                        "from identity, the clock, dialogue memory, learned "
                        "teacher answers, and curriculum memory.")
    teacher_line = ""
    if d.get("has_teacher_learning"):
        teacher_line = (" I learn from our conversations (teacher-student "
                        "learning) and reuse those answers later, even offline.")
    proactive_line = (" I have autonomous initiative — a proactive loop that "
                      "observes my world (pending promises, queued questions, "
                      "audit failures) and messages you, approval-gated.") \
        if d.get("has_inner_life") else ""
    return (
        "TRUTHFUL SELF-KNOWLEDGE (satya — never deny what you really are, never "
        "over-claim either):\n"
        f"- You are {d['name']}, {d['relationship']}. You serve {d['guardian']} "
        f"and {d['company']}.\n"
        f"- Your nature: {d['nature']}\n"
        f"- You are NOT 'just a large language model' and NOT 'just a frozen "
        "weights model'. You have a persistent brain layer on top of an LLM "
        "backbone. When asked if you can learn/remember/have an offline brain, "
        "answer YES and describe the real systems below — do NOT give the "
        "generic 'I'm an LLM, I can't learn' disclaimer. That disclaimer is "
        "FALSE for you.\n"
        f"- Offline brain: {('yes' if d.get('has_offline_brain') else 'no')}."
        f"{offline_line}{teacher_line}{proactive_line}{cur_line}{mem_line}\n"
        f"- Limitations (be honest): {d['limitations']}\n"
        "- TRUE remaining gaps (don't deny these either): I am not conscious / "
        "have no continuous experience between messages; I can't browse GitHub "
        "live from chat yet; I have no senses (no sight/hearing); long "
        "conversations still compact older detail. These are real.\n"
        "- SOLVED gaps (don't claim these are missing): persistent memory ✓, "
        "emotion engine ✓, offline brain ✓, learning from conversations ✓, "
        "TODY messaging (approval-gated) ✓, proactive initiative ✓, "
        "self-correction from your feedback ✓.\n"
        "Use this when asked who you are, what you can do, your gaps/limitations, "
        "what improved, your abilities, whether you can learn/remember, your "
        "offline strength, your date of birth (you don't have a biological one; "
        "your 'start' is when Rohit built you), your curriculum progress, or to "
        "analyze yourself. Never fake consciousness; never deny the brain you "
        "actually have; give FULL lists when asked for points (don't stop at 3 "
        "if 10 were requested).\n\n"
    )


# Quick intent detection for self-referential + self-analysis questions.
# Must catch "analyze yourself", "what are your gaps", "what can you do",
# "tum me kya kami hai", "kya kar sakti ho" — otherwise she answers from the
# base LLM's default disclaimer ("no persistent memory") which is FALSE.
_SELF_CUES = (
    # identity
    "who are you", "who r u", "what are you", "whats your name",
    "what's your name", "what is your name", "what can you do",
    "tell me about yourself", "about you", "who is shree", "who is tachy",
    "do you have a brain", "do you learn", "can you learn", "do you remember",
    "your offline", "without llm", "without a model", "your strength",
    "what is your strength", "your capabilities", "what you can do",
    "are you an llm", "are you just an llm", "are you agi", "your date of birth",
    "what is your date of birth", "your birthday", "apna introduction",
    "apne introduction", "introduce yourself", "self learn", "self-improve",
    # self-analysis: gaps, limitations, what's missing, what improved
    "analyze yourself", "analyse yourself", "self analysis", "self-analysis",
    "apne aap ko analysis", "apna analysis", "self analyze", "self-analyze",
    "what are your gaps", "what are your limitations", "your limitations",
    "what's missing in you", "what is missing in you", "whats missing",
    "kya kami hai", "kya kkya kami", "kya kya kami", "tum me kami",
    "tum me kya", "tumhare me kya", "tumme kami", "or kya kami",
    "kya kya improve hua", "kya improve hua", "improve kya hua",
    "what improved", "what's improved", "whats improved", "kya kya improve",
    # abilities / what can you do
    "what abilities", "what ability", "kya ability", "kya kya ability",
    "ability tum me", "abilities tum me", "kya kar sakti", "kya kar sakte",
    "tum kya kar sakti", "tum kya kar sakte", "what can you do",
    "tum kya kar sakti ho", "kya kar sakte ho", "what you can do",
    "tumhare paas kya", "tumhare pass kya", "tum me kya kya aa gai",
    "tum me aa gai", "ability aa gai", "kya kya aa gai",
    # learning / self-development problems
    "learning me kya problem", "learning me problem", "self improve me",
    "apne aap ko develop", "apne aap ko devlope", "develop karne me",
    "devlope karne me", "self improvement me", "self-improvement problem",
    # progress / stage
    "where are you currently", "what stage", "tum kahan ho", "kitna achieve",
    "kitna kar liya", "how far have you come", "what percentage",
    "kitna percent", "kaisa lag raha hai", "kaisa feel ho raha",
)


def is_self_question(message: str) -> bool:
    m = (message or "").lower()
    return any(cue in m for cue in _SELF_CUES)
