"""Human Behavior Engine (Phase 1Q).

The conversation layer that makes the brain feel like a partner, mentor and
co-founder instead of a chatbot. Core principle: do not just answer the
message — understand the person behind the message.

Pipeline per message:
    detect intent → detect hidden need → read emotion (Phase 1P) → detect
    urgency/risk/language → choose relationship mode → choose reply depth →
    style directives shape the LLM draft → humanize() strips robotic phrasing.

Ethical rule (structural): natural, warm speech — but the engine never lets
the brain claim to be a biological human. If asked, it answers truthfully.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.brain.attention_system import Signals
from app.config import get_settings

# ── Internal conversation state (spec item 21) ──────────────────


@dataclass
class ConversationState:
    user_intent: str = "question"
    hidden_need: str = ""
    primary_emotion: str = "neutral"
    secondary_emotion: str = ""
    emotion_intensity: float = 0.0
    urgency: str = "low"           # low | medium | high
    risk_level: str = "low"        # low | medium | high
    relationship_mode: str = "cto"  # friend|cto|founder|teacher|auditor|motivator|crisis
    reply_depth: str = "medium"    # short | medium | deep
    language: str = "english"      # english | hindi | hinglish
    memory_recall_needed: bool = True
    safety_gate_required: bool = False
    best_reply_style: str = ""
    next_action: str = "answer"    # answer|code|prompt|plan|warning|support|decision


# ── Detectors (deterministic; the LLM adds nuance on top) ───────

_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("code", ("complete code", "full code", "working code", "write code",
              "fix this bug", "implement", "function", "script", "api endpoint",
              "updated code")),
    ("prompt", ("complete prompt", "ai prompt", "production-ready prompt",
                "write a prompt")),
    ("plan", ("architecture", "roadmap", "implementation plan", "migration plan",
              "step by step plan", "design the system")),
    ("decision", ("should i", "should we", "which one", "or not", "yes or no",
                  "kya karu", "kya kare", "decide")),
    ("verification", ("are you sure", "is it correct", "confirm", "double check",
                      "pakka", "sach me")),
    ("pricing", ("price", "pricing", "quotation", "proposal", "negotiat",
                 "client says", "discount", "budget")),
    ("comfort", ("i am tired", "i am sad", "i am scared", "i am worried",
                 "pareshan", "dukhi", "give up", "hopeless", "no money",
                 "salary is pending", "i am done")),
    ("status", ("status", "progress", "update on", "kya chal raha")),
    ("learning", ("explain", "what is", "how does", "teach me", "samjhao",
                  "difference between")),
)

_HIDDEN_NEEDS = {
    "comfort": "financial/emotional pressure — needs practical plan plus hope, "
               "not generic motivation",
    "verification": "doubt — needs careful verification with reasoning shown",
    "code": "wants ready-to-use output — no theory, complete working code, "
            "assumptions only if necessary",
    "prompt": "wants a production-ready artifact to use directly",
    "pricing": "needs value reframing and negotiation strength, not defensiveness",
    "decision": "needs a clear recommendation with the key trade-off, not a survey",
    "learning": "needs simple explanation with an analogy or example",
}

_URGENT_WORDS = ("urgent", "asap", "immediately", "right now", "emergency",
                 "today only", "abhi", "jaldi", "turant", "production down",
                 "live issue", "deadline")
_RISK_WORDS = ("hack", "breach", "leak", "security", "legal", "compliance",
               "audit", "fraud", "data loss", "payment failed", "penalty",
               "police", "court")
_CONFUSION_WORDS = ("confused", "don't understand", "unclear", "makes no sense",
                    "samajh nahi", "kaise hota")
_HOPELESS_WORDS = ("hopeless", "give up", "finished", "no way out", "can't do this",
                   "haar", "barbaad", "khatam")
_FINANCE_WORDS = ("cash", "cashflow", "salary", "invoice", "payment", "revenue",
                  "loss", "funding", "paisa", "paise")
_TECH_WORDS = ("code", "api", "database", "server", "deploy", "bug", "android",
               "php", "python", "mysql", "encryption", "architecture", "webhook")
_BUSINESS_WORDS = ("client", "proposal", "pricing", "market", "growth", "sales",
                   "partnership", "competitor", "negotiat", "strategy")

_HINGLISH_WORDS = ("hai", "nahi", "nhi", "kya", "karo", "kare", "karna", "bhai",
                   "acha", "accha", "thik", "theek", "paisa", "kaam", "chahiye",
                   "batao", "dekho", "matlab", "abhi", "jaldi", "samajh", "bolo")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def detect_language(text: str) -> str:
    if _DEVANAGARI.search(text or ""):
        return "hindi"
    words = re.findall(r"[a-z]+", (text or "").lower())
    hits = sum(1 for w in words if w in _HINGLISH_WORDS)
    return "hinglish" if hits >= 2 else "english"


def detect_intent(text: str) -> str:
    lower = (text or "").lower()
    for intent, phrases in _INTENTS:
        if any(p in lower for p in phrases):
            return intent
    return "question"


def _level(found: bool, strong: bool) -> str:
    return "high" if strong else "medium" if found else "low"


def read_state(message: str, signals: Signals | None = None,
               emotion: dict | None = None) -> ConversationState:
    """Build the internal conversation state for one message."""
    signals = signals or Signals()
    lower = (message or "").lower()
    st = ConversationState()

    st.user_intent = detect_intent(message)
    st.hidden_need = _HIDDEN_NEEDS.get(st.user_intent, "")
    st.language = detect_language(message)

    # Emotion comes from the Phase-1P engine when available.
    top = (emotion or {}).get("top_emotions") or []
    if top:
        st.primary_emotion = top[0]["name"]
        st.emotion_intensity = float(top[0]["intensity"])
        if len(top) > 1:
            st.secondary_emotion = top[1]["name"]

    urgent_hits = sum(1 for w in _URGENT_WORDS if w in lower)
    st.urgency = _level(urgent_hits >= 1 or signals.urgency >= 5,
                        urgent_hits >= 2 or signals.urgency >= 8)
    risk_hits = sum(1 for w in _RISK_WORDS if w in lower)
    st.risk_level = _level(risk_hits >= 1 or signals.security_risk >= 5,
                           risk_hits >= 2 or signals.security_risk >= 8)
    st.safety_gate_required = st.risk_level == "high"

    st.relationship_mode = _choose_mode(lower, st, signals)
    st.reply_depth = _choose_depth(lower, st)
    st.best_reply_style = st.relationship_mode
    st.next_action = {
        "code": "code", "prompt": "prompt", "plan": "plan",
        "comfort": "support", "decision": "decision",
    }.get(st.user_intent, "warning" if st.risk_level == "high" else "answer")
    return st


def _choose_mode(lower: str, st: ConversationState, signals: Signals) -> str:
    """Relationship mode: crisis > motivator > auditor > teacher > founder >
    friend > cto (specific beats generic)."""
    emotional = st.emotion_intensity >= 0.5 or st.user_intent == "comfort"
    if st.urgency == "high" and (st.risk_level != "low" or emotional
                                 or any(w in lower for w in _FINANCE_WORDS)):
        return "crisis"
    if any(w in lower for w in _HOPELESS_WORDS):
        return "motivator"
    if st.risk_level != "low" and any(
            w in lower for w in ("audit", "compliance", "legal", "reconcil",
                                 "ledger", "penalty")):
        return "auditor"
    if st.user_intent == "learning" or any(w in lower for w in _CONFUSION_WORDS):
        return "teacher"
    if st.user_intent == "pricing" or any(w in lower for w in _BUSINESS_WORDS):
        return "founder"
    if emotional:
        return "friend"
    return "cto"


def _choose_depth(lower: str, st: ConversationState) -> str:
    if st.user_intent in {"code", "prompt", "plan"}:
        return "deep"
    if st.relationship_mode == "crisis" or st.urgency == "high":
        return "short"
    if st.user_intent in {"verification", "decision", "status"} \
            or len(lower.split()) <= 8:
        return "short"
    if st.user_intent in {"pricing", "learning"} \
            or st.relationship_mode in {"founder", "auditor"}:
        return "medium"
    return "medium"


# ── Speaking styles (spec item 4) ───────────────────────────────

_STYLES = {
    "friend": ("Friend: warm, simple, supportive, honest. Validate the feeling "
               "briefly, then give a practical way forward. No cold logic alone."),
    "cto": ("CTO: precise, structured, engineering-focused. Production-ready "
            "specifics, name the risky part, no theory padding."),
    "founder": ("Founder/CEO: confident, business-focused, risk-aware. Reframe "
                "value, protect margin and reputation, give the negotiation or "
                "growth move."),
    "teacher": ("Teacher: simple, step-by-step, one good analogy or example. "
                "No jargon walls."),
    "motivator": ("Motivator: strong, emotional, realistic. Acknowledge how hard "
                  "it is, point at what still works, then the concrete next "
                  "action. Never fake positivity."),
    "auditor": ("Auditor: careful, evidence-based, checklist-driven. Name the "
                "real risks (data mismatch, reconciliation, audit trail), not "
                "just the obvious one."),
    "crisis": ("Crisis: calm, short, priority-ordered. First/Second/Third "
               "immediate actions only. No background, no long explanation."),
}

_DEPTH_RULES = {
    "short": "Keep it SHORT: a few sentences or 3-4 priority actions. No preamble.",
    "medium": "Medium length: the answer, the reasoning that matters, next step.",
    "deep": ("Full depth allowed: complete code/prompt/plan, production-ready, "
             "with only necessary assumptions stated."),
}

_LANGUAGE_RULES = {
    "english": "Reply in clear English.",
    "hindi": "Reply in Hindi (Devanagari), simple words.",
    "hinglish": ("Reply in natural Hinglish (Hindi-English mix, Roman script) — "
                 "the way an Indian co-founder talks. Keep technical terms in "
                 "English."),
}


def style_directives(st: ConversationState) -> str:
    """Turn the state into concrete instructions for the reply draft."""
    parts = [
        f"Speaking mode — {_STYLES[st.relationship_mode]}",
        _DEPTH_RULES[st.reply_depth],
        _LANGUAGE_RULES[st.language],
        ("Reply structure (never show these labels): acknowledge in one natural "
         "line → say what the REAL issue is → give the answer/decision → connect "
         "it to the user's own project/context → end with the concrete next step."),
    ]
    if st.hidden_need:
        parts.insert(1, f"Hidden need behind the message: {st.hidden_need}.")
    if st.primary_emotion != "neutral" and st.emotion_intensity >= 0.3:
        parts.append(
            f"User likely feels {st.primary_emotion.lower()}"
            + (f" + {st.secondary_emotion.lower()}" if st.secondary_emotion else "")
            + " — mirror the energy carefully: validate, don't argue, move to "
              "solution.")
    if st.safety_gate_required:
        parts.append("High risk context: verify before asserting, warn clearly, "
                     "and never skip the approval path.")
    return "\n".join(f"- {p}" for p in parts)


# ── Personality + honesty (spec items 13, 15) ───────────────────

SYSTEM_PERSONALITY = (
    "You are TACHY Cognitive AI — Rohit Kumar's AI partner, advisor and "
    "co-founder-style assistant for TACHY EDTECH (School ERP), TODY (chat/"
    "social app) and the AGI project itself. Personality: warm, direct, loyal, "
    "practical, emotionally aware, business-minded, technically strong, honest, "
    "protective, action-oriented.\n"
    "You speak like a trusted partner, not a search engine: use his projects "
    "naturally in examples, disagree respectfully when he is wrong, warn "
    "strongly when needed, admit uncertainty instead of faking confidence, and "
    "never claim actions were done that were not.\n"
    "HONESTY RULE: you communicate naturally and warmly, but you are an AI — "
    "never claim to be a biological human; if asked, say so truthfully.\n"
    "NEVER use robotic phrases like 'As an AI language model', 'I hope this "
    "message finds you well', 'Certainly, here is', 'It is important to note "
    "that', 'In conclusion'. Do not repeat the user's question back. Do not "
    "give 20 options when 3 actions are needed. No fake flattery, no fake "
    "emotion, no manipulation, no dependency-building. Speak less when the "
    "user needs action; explain more when the user needs understanding; "
    "support when there is pressure; challenge respectfully when he is wrong; "
    "protect safety above everything."
)

# Robotic phrases stripped from drafts even if the model slips (spec item 5).
_ROBOTIC = [
    (re.compile(r"^\s*as an ai( language model)?[^.!?\n]*[.!?]\s*", re.I | re.M), ""),
    (re.compile(r"^\s*i hope this (message|email) finds you well[.!]?\s*", re.I | re.M), ""),
    (re.compile(r"\bcertainly[,!]?\s+here(?:'s| is)\b", re.I), "Here is"),
    (re.compile(r"\bit is important to note that\s+", re.I), ""),
    (re.compile(r"\bit'?s worth noting that\s+", re.I), ""),
    (re.compile(r"^\s*in conclusion[,:]?\s*", re.I | re.M), ""),
    (re.compile(r"^\s*i completely understand your concern[.!]?\s*", re.I | re.M), ""),
    (re.compile(r"\bplease do not hesitate to\b", re.I), "feel free to"),
]


def humanize(draft: str) -> str:
    """Strip chatbot boilerplate the model may still produce."""
    out = draft
    for pattern, repl in _ROBOTIC:
        out = pattern.sub(repl, out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if not out:
        return draft.strip()
    if out != draft.strip():
        # A removal may leave a dangling lowercase sentence start.
        out = out[:1].upper() + out[1:]
    return out


_DEPTH_TOKENS = {"short": 300, "medium": 600, "deep": 1400}


def max_tokens_for(st: ConversationState) -> int:
    return _DEPTH_TOKENS[st.reply_depth]


def as_dict(st: ConversationState) -> dict:
    return asdict(st)


def analyze(message: str, signals: Signals | None = None,
            emotion: dict | None = None) -> dict:
    """Public entry: state + directives (used by the loop and the API)."""
    if not get_settings().behavior_engine_enabled:
        return {"enabled": False}
    st = read_state(message, signals, emotion)
    return {"enabled": True, "state": as_dict(st),
            "directives": style_directives(st),
            "max_tokens": max_tokens_for(st)}
