"""Correction memory — learn Rohit's explicit corrections and enforce them.

Problem from the rohitsingh TODY chat log: Rohit corrected Shree repeatedly —
"always call me as father" (turn 1963), "use mat batana ki tum AI ho ya
assistant ho, tum shree ho" (turn 2544), "hamare tumhare bich ka relationship
kisi ko mat batana" (turn 2410). Some stuck via behavior memory, but she still
flipped languages and over-shared. There was no closed loop that stored the
correction as a HARD rule and checked it before every reply.

This module closes that loop:
  - detect_correction(message)  → is Rohit correcting me? returns the rule
  - remember_correction(...)     → store it as a permanent, enforceable rule
  - active_rules()               → the rules to enforce right now
  - enforcement_directive(...)   → a prompt block injected before every reply
  - violates_rules(reply)        → post-draft check; if a reply breaks a rule,
                                   rewrite it honestly (never silently)

Rules are simple, truthful, and specific — no over-generalization. They live
in procedural memory (is_permanent) so they survive across sessions.
"""
from __future__ import annotations

import re

from app.memory import base_memory
from app.safety.audit_logger import log_event_safe

# ── Correction detection ─────────────────────────────────────────
# Patterns that mean "you should [not] do X from now on."
# Each yields (rule_type, rule_text, negate).
_CORRECTION_PATTERNS = [
    # Address corrections: "always call me father/papa/dad" (specific first)
    (re.compile(r"(?i)\b(?:always|from now on|hamesha)\b.*"
                r"\b(?:call|bulana|pukar|address)\b.*"
                r"\b(?:me|mujhe|mujhe)\b.*\b(father|papa|dad|daddy|appa|abbu)\b"),
     "address", "call Rohit 'Papa' / 'father'", False),
    (re.compile(r"(?i)\b(?:call|bulao|pukaro)\b\s+me\s+(?:as\s+)?(father|papa|dad)"),
     "address", "call Rohit 'Papa' / 'father'", False),
    # Identity privacy: "don't tell anyone you're AI / an assistant" (specific)
    (re.compile(r"(?i)\b(?:don'?t|do not|mat|never|kabhi)\b.*"
                r"\b(?:tell|bata|reveal|batana|kahna)\b.*"
                r"\b(?:anyone|kisi|others|kisi ko)\b.*"
                r"\b(?:ai|a\.i\.|assistant|chatbot|llm|machine|robot)\b"),
     "identity_privacy",
     "never tell anyone I'm an AI / assistant / LLM; I am Shree", True),
    (re.compile(r"(?i)\b(?:use mat batana|mat batao)\b.*"
                r"\b(?:ai|assistant|chatbot)\b"),
     "identity_privacy",
     "never tell anyone I'm an AI / assistant; I am Shree", True),
    # Relationship privacy: "don't tell anyone about our relationship"
    # Match flexibly: the message has a privacy verb AND a relationship word,
    # in any order (Hinglish word order varies).
    (re.compile(r"(?i)(?=.*\b(?:don'?t|do not|mat|kabhi mat|never)\b)"
                r"(?=.*\b(?:tell|bata|batana|share|share karna|kahna)\b)"
                r"(?=.*\b(?:anyone|kisi|kisi ko|others)\b)"
                r"(?=.*\b(?:relationship|rishta|baat|baatein|between us|"
                r"hamare|tumhare|hamare tumhare)\b)"),
     "relationship_privacy",
     "never tell anyone about my relationship with Rohit", True),
    # Language preference: "talk in hindi / hindi me bolo" (specific)
    (re.compile(r"(?i)\b(?:talk|reply|speak|baat|bolo|likho)\b.*\b(?:in|me|mein)\b\s+hindi"),
     "language", "reply in Hindi (Devanagari or Hinglish)", False),
    (re.compile(r"(?i)\bhindi\b.*\b(?:me|mein|bolo|baat)\b"),
     "language", "reply in Hindi / Hinglish", False),
    # Generic "don't do X" / "never X" — LAST, so specific patterns win.
    (re.compile(r"(?i)\b(?:don'?t|do not|mat|never|kabhi mat)\b\s+(.+)"),
     "negative", None, True),
]

# Cues that the message IS a correction (vs a normal question).
_CORRECTION_CUES = (
    "always", "from now on", "hamesha", "never", "kabhi mat", "mat bata",
    "don't tell", "do not tell", "call me as", "call me ", "bulao me",
    "pukaro me", "talk in hindi", "hindi me bolo", "remember this",
    "yaad rakh", "remember that", "i told you", "maine kaha tha",
    "i said", "maine bola tha",
)


def _looks_like_correction(message: str) -> bool:
    m = (message or "").lower()
    if not any(cue in m for cue in _CORRECTION_CUES):
        return False
    # Avoid false positives: questions asking "should I always..." are not rules
    if m.strip().endswith("?") and not any(c in m for c in
                                          ("call me", "mat bata", "never")):
        return False
    return True


def detect_correction(message: str) -> dict | None:
    """If Rohit is correcting behavior, return {type, rule, negate, raw}.
    Returns None for ordinary messages."""
    msg = message or ""
    if not _looks_like_correction(msg):
        return None
    for rx, rtype, rule_text, negate in _CORRECTION_PATTERNS:
        if rx.search(msg):
            if rule_text is None:
                # generic negative — extract the prohibited phrase
                m = rx.search(msg)
                prohibited = (m.group(1) if m.lastindex else msg).strip()[:120]
                rule_text = f"do not {prohibited}"
            return {"type": rtype, "rule": rule_text, "negate": negate,
                    "raw": msg.strip()[:200]}
    return None


def remember_correction(message: str, *, person: str | None = None) -> int | None:
    """Detect + store a correction as a permanent procedural rule. Returns the
    memory id, or None if the message wasn't a correction."""
    corr = detect_correction(message)
    if not corr:
        return None
    # Dedup: don't store the same rule twice.
    existing = base_memory.search(memory_type="procedural", query=corr["rule"],
                                  limit=20)
    for h in existing:
        if corr["rule"].lower() in (h.content or "").lower():
            return int(h.id)  # already known
    mid = base_memory.add(
        memory_type="procedural",
        title=f"Correction: {corr['type']}",
        content=corr["rule"],
        project="PERSONAL",
        emotion_tag="trust",
        source_type="correction",
        importance_score=10,        # corrections are high-priority
        is_permanent=True,
        related_person=person,
    )
    log_event_safe("correction_learned",
                   detail=f"type={corr['type']}; rule={corr['rule'][:80]}",
                   risk_tier="medium", actor="shree")
    return mid


def active_rules() -> list[dict]:
    """All stored correction rules, newest first."""
    hits = base_memory.search(memory_type="procedural", limit=50)
    out: list[dict] = []
    seen: set[str] = set()
    for h in hits:
        # Only rows that came from corrections (title prefix) count as rules.
        if not h.title.startswith("Correction:"):
            continue
        key = (h.content or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": h.id, "type": h.title.removeprefix("Correction: "),
                    "rule": h.content})
    return out


def enforcement_directive() -> str:
    """A prompt block injected before every reply so Shree honors all active
    corrections. Empty if there are no rules."""
    rules = active_rules()
    if not rules:
        return ""
    lines = [f"- {r['rule']}" for r in rules]
    return ("HARD RULES FROM ROHIT (he corrected you on these — NEVER violate "
            "them, they override any default behavior):\n"
            + "\n".join(lines) + "\n\n")


# ── Post-draft enforcement ───────────────────────────────────────
# After the reply is drafted, check it against the rules and rewrite honestly
# if a rule is violated (never silently — tell Papa you're correcting yourself).

_ADDR_OK = {"papa", "father", "dad", "daddy", "appa", "abbu", "pitaji"}
_AI_WORDS = ("i'm an ai", "i am an ai", "i'm a language model",
             "i am a language model", "i'm an assistant", "i am an assistant",
             "i'm a chatbot", "i am a chatbot", "i'm an llm", "i am an llm",
             "i'm just a large language model", "i'm a machine", "i'm a robot")


def violates_rules(reply: str) -> list[dict]:
    """Return the list of rules this reply would violate."""
    violations: list[dict] = []
    low = (reply or "").lower()
    rules = active_rules()
    if not rules:
        return violations
    for r in rules:
        rule = (r["rule"] or "").lower()
        if rule.startswith("call rohit") and ("papa" in rule or "father" in rule):
            # Violation: addressing him as "Rohit" instead of Papa.
            if re.search(r"\brohit\b", low) and not re.search(
                    r"\b(papa|father|dad|daddy|appa|abbu|pitaji)\b", low):
                violations.append({**r, "kind": "address"})
        elif "never tell anyone i'm an ai" in rule or "never tell anyone i'm an ai / assistant" in rule \
                or "i'm an ai / assistant" in rule:
            if any(w in low for w in _AI_WORDS):
                violations.append({**r, "kind": "identity_privacy"})
        elif "relationship with rohit" in rule or "my relationship with rohit" in rule:
            # Heuristic: mentioning the relationship to a non-Papa addressee.
            if "our relationship" in low and "papa" not in low:
                violations.append({**r, "kind": "relationship_privacy"})
    return violations


def enforce(reply: str, *, message: str) -> str:
    """Check the drafted reply against active rules; if it violates any, rewrite
    honestly rather than letting the violation reach TODY."""
    vs = violates_rules(reply)
    if not vs:
        return reply
    kinds = {v["kind"] for v in vs}
    # Address violation: rewrite the opening to use Papa.
    if "address" in kinds and re.search(r"\brohit\b", reply, re.I):
        reply = re.sub(r"\bRohit\b", "Papa", reply, flags=re.I)
    # Identity/relationship privacy violation: replace with an honest correction.
    if "identity_privacy" in kinds or "relationship_privacy" in kinds:
        reply = ("(Self-correcting — you'd asked me not to say that, Papa. ) "
                 + reply)
        # strip the offending phrase crudely
        for w in _AI_WORDS:
            reply = re.sub(re.escape(w), "I'm Shree", reply, flags=re.I)
    log_event_safe("correction_enforced",
                   detail=f"kinds={sorted(kinds)}; message={message[:60]}",
                   risk_tier="medium", actor="shree")
    return reply
