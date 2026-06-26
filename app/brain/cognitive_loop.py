"""Cognitive loop — the spine that ties the brain together.

NEED → INTEREST → ATTENTION → OBSERVATION → EMOTION → MEMORY → MEANING →
DECISION → ACTION → REVIEW → LEARNING

Phase 1A: a working skeleton that scores attention and routes by band. Memory
recall, LLM reasoning, and the learning write-back are filled in 1B/1C.
"""
from __future__ import annotations

from dataclasses import asdict

from app.brain import identity_core
from app.brain.attention_system import Signals, attention_band, priority_score


def process(message: str, signals: Signals | None = None) -> dict:
    """Run one pass of the loop over an incoming message.

    Returns a structured trace so the API/UI can show *why* the brain reacted
    the way it did — transparency is a first-class requirement.
    """
    signals = signals or Signals()
    score = priority_score(signals)
    band = attention_band(score)

    return {
        "identity": identity_core.IDENTITY.name,
        "guardian": identity_core.IDENTITY.guardian,
        "input": message,
        "signals": asdict(signals),
        "priority_score": score,
        "attention_band": band,
        # placeholders for later phases:
        "relevant_memory": [],      # 1B: recall from cognitive_memories
        "decision": None,           # 1B: decision_engine output
        "reply": _draft_reply(message, band),
        "should_remember": score >= 35,
    }


def _draft_reply(message: str, band: str) -> str:
    """Stub responder until the LLM provider interface is wired (Phase 1B)."""
    return (
        f"[{band} attention] Received: '{message[:120]}'. "
        "Reasoning + memory recall land in Phase 1B."
    )
