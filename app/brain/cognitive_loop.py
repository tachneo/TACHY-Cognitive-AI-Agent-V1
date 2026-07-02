"""Cognitive loop — the spine that ties the brain together.

NEED → INTEREST → ATTENTION → OBSERVATION → EMOTION → MEMORY → MEANING →
DECISION → ACTION → REVIEW → LEARNING

Phase 1B: full pass — classify need/interest, score attention, recall memory,
run the decision engine, draft a reply via the LLM provider, self-review, and
write the lesson back to memory.
"""
from __future__ import annotations

from dataclasses import asdict

from app.brain import identity_core, interest_system, need_system, self_review
from app.brain.attention_system import Signals, attention_band, priority_score
from app.brain.decision_engine import as_dict as decision_dict
from app.brain.decision_engine import decide
from app.brain.feedback import apply_feedback
from app.brain.learning_engine import learn
from app.brain.nurture_engine import dharma_check
from app.llm.provider import get_provider
from app.memory.behavior_memory import recall_preferences

_SYSTEM_PROMPT = (
    "You are TACHY Cognitive AI, guardian Rohit Kumar. You are not a chatbot but "
    "a cognitive assistant with memory, emotion-aware priority, and safety rules. "
    "Be practical and production-ready, never generic. Honour the approval policy: "
    "never claim to have taken a high-risk action; recommend and request approval."
)


def process(message: str, signals: Signals | None = None,
            context: str | None = None) -> dict:
    """Run one full pass of the loop and return a transparent trace."""
    signals = signals or Signals()
    feedback = apply_feedback(message)

    # NEED + INTEREST + ATTENTION
    need = need_system.classify(message)
    interest = interest_system.interest_score(message)
    if interest["score"]:
        signals.guardian_interest = max(signals.guardian_interest, interest["score"])
    score = priority_score(signals)
    band = attention_band(score)

    # MEMORY + MEANING + DECISION
    decision = decide(message)
    decision_d = decision_dict(decision)
    dharma = dharma_check(decision_d.get("action", message),
                          risk_tier=decision_d.get("risk_tier", "low"))

    # ACTION (LLM reply, grounded by the decision + recalled memory)
    reply = _draft_reply(message, band, decision_d, context=context, dharma=dharma)

    # REVIEW
    review = self_review.review(message=message, reply=reply, decision=decision_d)

    # LEARNING
    learned = learn(message=message, decision=decision_d, review=review, signals=signals)

    return {
        "identity": identity_core.IDENTITY.name,
        "guardian": identity_core.IDENTITY.guardian,
        "input": message,
        "context": context,
        "need": need,
        "interest": interest,
        "signals": asdict(signals),
        "priority_score": score,
        "attention_band": band,
        "decision": decision_d,
        "dharma": dharma,
        "reply": reply,
        "feedback": feedback,
        "self_review": review,
        "learning": learned,
    }


def _draft_reply(message: str, band: str, decision: dict,
                 context: str | None = None,
                 dharma: dict | None = None) -> str:
    """Generate the reply through the configured LLM provider, grounded by the
    decision trace. Falls back to the heuristic provider when no key is set."""
    recalled = decision.get("recalled", [])
    memo = "\n".join(f"- {m['title']}" for m in recalled) or "- (none yet)"
    preferences = recall_preferences(message, limit=5)
    prefs = "\n".join(
        f"- {p['title']}: {p['content'][:300]}" for p in preferences
    ) or "- Prefer direct, practical, production-ready answers."
    context_block = f"Conversation/context:\n{context}\n\n" if context else ""
    prompt = (
        context_block
        + f"User message ({band} attention): {message}\n\n"
        f"Project: {decision['project']} | Action: {decision['action']} | "
        f"Risk: {decision['risk_tier']} | Approval needed: {decision['requires_approval']}\n"
        f"Relevant memory:\n{memo}\n\n"
        f"Learned behavior/style preferences:\n{prefs}\n\n"
        f"Bhagavad Gita dharma check:\n{dharma or {}}\n\n"
        f"Chosen approach: {decision['chosen']}\n"
        "Write a concise, practical reply with a clear next step. Adapt tone to "
        "learned preferences, but do not fake certainty or claim actions were done."
    )
    try:
        return get_provider().complete(_SYSTEM_PROMPT, prompt)
    except Exception as exc:  # never let an LLM/network error break the loop
        return (
            f"[reply fallback — LLM provider error: {type(exc).__name__}]\n"
            f"Plan: {decision['chosen']} (project {decision['project']}, "
            f"risk {decision['risk_tier']})."
        )
