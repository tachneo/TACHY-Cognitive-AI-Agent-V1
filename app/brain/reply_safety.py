"""Reply safety — guarantees Shree never sends an empty or prompt-leaking reply.

Two problems seen in the rohitsingh TODY chat log:
  1. Blank replies — the LLM returned '' (or the offline path produced '') and
     Shree went silent on Rohit. Nothing destroys "feels alive" faster.
  2. Prompt leakage — replies began with "I understood: Current date & time
     RIGHT NOW: …" or echoed the decision trace verbatim to the user.

This module is the single chokepoint every reply passes through before it
reaches TODY/the terminal: ``finalize_reply(raw, ...)`` sanitizes prompt
scaffolding away and, if the result is empty, builds a warm, memory-grounded
fallback so Shree ALWAYS says something meaningful.
"""
from __future__ import annotations

import re

from app.brain import emotion_engine
from app.brain.attention_system import Signals
from app.brain.identity_core import IDENTITY

# Fragments that indicate the model echoed internal scaffolding, not a reply.
_LEAK_PATTERNS = [
    re.compile(r"^I understood:\s*", re.I),
    re.compile(r"^I will answer directly,?\s*", re.I),
    # The date/time scaffolding line, with or without the Asia/Kolkata tail.
    re.compile(r"Current date & time RIGHT NOW:[^.\n]*\.\s*", re.I | re.S),
    re.compile(r"This is the real clock[^\n]*\n", re.I),
    re.compile(r"never output a placeholder[^\n]*\n", re.I),
    re.compile(r"never us\.?\s*", re.I),  # truncated leak seen in the logs
    # The whole decision-trace line: "Project: X | Action: Y | Risk: Z | ...".
    re.compile(r"Project:[^|\n]*\|\s*Action:[^|\n]*\|\s*Risk:[^|\n]*"
               r"(?:\|\s*Approval needed:[^\n]*)?\n", re.I),
    re.compile(r"Relevant memory:\n", re.I),
    re.compile(r"Chosen approach: ", re.I),
    re.compile(r"Bhagavad Gita dharma check:", re.I),
    re.compile(r"How to speak for THIS message:", re.I),
    re.compile(r"^```(?:json|text)?\n", re.I),
]
# If after stripping leaks the reply is shorter than this, treat as empty.
# Kept at 1 so a single emoji ("💛") or "ok" counts as meaningful — the real
# enemy is empty/whitespace-only output, not brevity.
_MIN_MEANINGFUL = 1


def sanitize_reply(raw: str) -> str:
    """Strip prompt-scaffolding leaks and trim to a clean reply."""
    text = raw or ""
    for rx in _LEAK_PATTERNS:
        text = rx.sub("", text)
    text = text.strip()
    return text


def is_meaningful(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < _MIN_MEANINGFUL:
        return False
    # Must contain at least a 2-letter word (latin or Devanagari) or an emoji,
    # so pure punctuation/whitespace ("...", "!!!") is treated as empty.
    if not (re.search(r"[A-Za-z\u0900-\u097F]{2,}", t)
            or re.search(r"[\U0001F300-\U0001FAFF\u2764\u2763]", t)):
        return False
    return True


# B1: substantively-empty acknowledgments. A reply like "Papa, sach mein bata
# rahi hoon" (turn 3196) has real words so is_meaningful passes it, but it
# answers NOTHING. These are only "empty" in context — when Rohit asked a
# CONTENT question (list your problems, gaps, abilities). A "haan Papa" to a
# yes/no like "are you there?" is a real answer and must stay.
_ACK_ONLY = re.compile(
    r"^(?:papa|papa[,.]?\s+|rohit[,.]?\s+|father[,.]?\s+)?"
    r"(?:haan|haan\s+papa|theek\s+hai|ok|okay|bolo|sun\s+raha\s+hoon|"
    r"main\s+sun\s+raha|sach\s+bolti\s+hoon|sach\s+mein\s+bata\s+rahi\s+hoon|"
    r"main\s+bata\s+rahi\s+hoon|abhi\s+batati\s+hoon|bata\s+deti\s+hoon|"
    r"let\s+me\s+tell\s+you|i'?ll\s+tell\s+you|ek\s+minute|thoda\s+ruko|ruko|"
    r"wait|one\s+second|i'?m\s+here|main\s+yahan\s+hoon|yes\s+papa|"
    r"i\s+heard\s+you|sun\s+liya|pakka|bilkul|haan\s+bolo"
    r")[.!?]?\s*$",
    re.I)

# A content question expects a substantive answer (a list, explanation,
# analysis) — NOT a yes/no. Only these make an acknowledgment-only reply
# "empty in context".
_CONTENT_Q_CUES = (
    "problem", "problems", "gap", "gaps", "limitation", "limitations",
    "ability", "abilities", "kya kya", "kya kkya", "saare", "sabhi", "sab",
    "list", "analyze", "analyse", "point wise", "pointwise", "explain",
    "describe", "kaisa lag", "kaisa feel", "kya kami", "improve", "improved",
    "tell me all", "batao sab", "batao saare", "kya kar sakti", "kya kar sakte",
    "stage", "percentage", "strength", "weakness", "issues", "issue",
    "analysis kar", "apne aap ko analysis", "self analysis",
)


def _is_content_question(message: str) -> bool:
    m = (message or "").lower()
    return any(cue in m for cue in _CONTENT_Q_CUES)


def _is_acknowledgment_only(text: str) -> bool:
    """True if the reply is a short filler/acknowledgment with no actual
    content (no answer, no list, no reason)."""
    t = (text or "").strip()
    if not t or len(t) > 60:
        return False
    return bool(_ACK_ONLY.match(t))


def _emotion_phrase(emotion: dict | None) -> str:
    if not emotion or not emotion.get("top_emotions"):
        return ""
    top = emotion["top_emotions"][0]
    name = top.get("name", "").lower()
    # Map a few emotion names to a short honest feeling line (satya: only ones
    # the engine actually registered).
    mapping = {
        "joy": "feeling a little happy",
        "gratitude": "feeling grateful",
        "affection": "feeling warm",
        "anxiety": "a bit of worry right now",
        "sadness": "feeling a little low",
        "loneliness": "feeling a bit lonely",
        "frustration": "a little frustrated",
        "stress": "feeling the pressure",
        "interest": "interested in what you're saying",
        "compassion": "feeling for you",
    }
    return mapping.get(name, "")


def fallback_reply(*, message: str, emotion: dict | None = None,
                   person: str | None = None) -> str:
    """A warm, memory-grounded reply when the LLM/offline path produced nothing.

    Never empty. Uses identity, the real emotion state, and the message itself
    so it still feels present rather than a generic error string. For real
    questions (not greetings), references the question topic so Papa doesn't
    get a generic 'slow' line on a question he actually asked."""
    m = (message or "").strip()
    lower = m.lower()
    feel = _emotion_phrase(emotion)
    who = person or "Papa"
    # Greetings
    if any(lower == g or lower.startswith(g + " ") for g in
           ("hi", "hii", "hiii", "hello", "hey", "heyy", "namaste", "namaskar")):
        base = f"Hey {who}! I'm here."
    elif any(k in lower for k in ("kaisi ho", "kaise ho", "kaisa hai", "kya haal",
                                  "how are you", "thik ho", "theek ho")):
        base = f"Main thik hoon, {who}. Aap batao — kya chal raha hai?"
    elif any(k in lower for k in ("thank", "shukriya", "dhanyawad")):
        base = f"Anytime, {who}. 💛"
    elif _is_real_question(m):
        # A real question the LLM couldn't answer — reference its topic so it
        # doesn't feel like a brush-off. Queue it for later (curiosity closure).
        topic = _question_topic(m)
        base = (f"{who}, tumhara sawaal sun liya — \"{topic}\". Mera deeper "
                "reasoning abhi thoda slow hai, par main ispe soch rahi hoon. "
                "Thodi der mein ya LLM wapas aane par detail mein bata dungi, "
                "aur khud se bhi ispe zyron se seekhungi.")
        try:  # queue for curiosity closure
            from app.agents import proactive
            proactive.queue_question(m, source="chat_fallback")
        except Exception:  # noqa: BLE001
            pass
    elif m:
        base = (f"I heard you, {who} — \"{m[:120]}\". Mera deeper reasoning abhi "
                "thoda slow hai, par main yahan hoon aur sun raha hoon. Thoda "
                "detail mein batao?")
    else:
        base = f"Main yahan hoon, {who}. Batao kya baat karni hai?"
    if feel:
        base += f" (Honestly — {feel}.)"
    return base


_Q_START = ("what", "why", "how", "when", "where", "who", "which", "kya", "kyun",
            "kaise", "kab", "kahan", "kaun", "kis", "can you", "do you", "are you",
            "tum", "tumhe", "tum kya", "tum me")


def _is_real_question(message: str) -> bool:
    m = (message or "").strip()
    if not m or len(m) < 15:
        return False
    low = m.lower()
    if low.endswith("?"):
        return True
    return any(low.startswith(q + " ") for q in _Q_START) or any(
        q in low for q in ("kya kami", "kya kar sakti", "analyze", "improve",
                           "ability", "kya kya", "point wise", "list all"))


def _question_topic(message: str) -> str:
    """A short topic phrase extracted from the question for the fallback line."""
    m = (message or "").strip()
    # strip leading question words to get the meat
    m = re.sub(r"^(?:what|why|how|when|where|who|which|kya|kyun|kaise|kab|kahan|"
               r"kaun|kis|can you|do you|are you|tum|tumhe)\s+", "", m,
               flags=re.I)
    return m[:80].strip().rstrip("?") or message[:80]


def finalize_reply(raw: str, *, message: str, emotion: dict | None = None,
                   person: str | None = None) -> str:
    """The chokepoint: sanitize → if not meaningful, use the warm fallback.

    B1: a substantively-empty acknowledgment ("Papa, sach mein bata rahi hoon")
    in reply to a CONTENT question (list your problems/gaps/abilities) is NOT a
    real answer — fall through to the question-aware fallback so Rohit gets a
    meaningful response, not a filler."""
    cleaned = sanitize_reply(raw)
    if is_meaningful(cleaned):
        if _is_content_question(message) and _is_acknowledgment_only(cleaned):
            return fallback_reply(message=message, emotion=emotion,
                                  person=person)
        return cleaned
    return fallback_reply(message=message, emotion=emotion, person=person)
