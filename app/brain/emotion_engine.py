"""Emotion Intelligence Module (Phase 1P).

Emotions here are NOT uncontrolled feelings. They are weighted internal
priority signals for reasoning, memory weight, safety, learning, social
behavior, and action selection — appraised deterministically from the input,
the brain's Signals, emotional memory, and a persistent mood baseline.

Hard rule (enforced structurally, not by convention): no emotion can override
safety, ethics, user permission, truth verification, or dharma/duty logic.
The engine outputs ADVISORY data only — an emotional_weight (0..10) that feeds
the attention formula, action-bias suggestions, and caution flags. It has no
path to lower a risk tier, skip an approval, or change the safety policy.

FINAL AGI PRINCIPLE:
    Emotion detects priority. Reason checks truth. Dharma checks right action.
    Safety prevents harm. Memory learns the result.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from app.brain.attention_system import Signals
from app.config import get_settings
from app.memory import base_memory, emotional_memory
from app.safety.audit_logger import log_event

# ── Taxonomy ────────────────────────────────────────────────────

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "emotion_taxonomy.csv"

_VALENCE_NUM = {"Positive": 1.0, "Negative": -1.0, "Neutral": 0.0, "Mixed": 0.0}
_AROUSAL_NUM = {"Low": 0.25, "Medium": 0.5, "High": 0.75, "Very_High": 1.0}


@dataclass(frozen=True)
class Emotion:
    category: str
    name: str
    valence: str
    arousal: str
    control_level: str
    action_bias: str
    agi_usage: str


@lru_cache
def taxonomy() -> dict[str, Emotion]:
    """All emotions keyed by name. Duplicated names across categories keep the
    first (most primary) definition; category listings use taxonomy_rows()."""
    out: dict[str, Emotion] = {}
    for row in taxonomy_rows():
        out.setdefault(row.name, row)
    return out


@lru_cache
def taxonomy_rows() -> tuple[Emotion, ...]:
    with _CSV_PATH.open(encoding="utf-8") as fh:
        return tuple(
            Emotion(
                category=r["category"].strip(),
                name=r["emotion_name"].strip(),
                valence=r["valence"].strip(),
                arousal=r["arousal"].strip(),
                control_level=r["control_level"].strip(),
                action_bias=r["default_action_bias"].strip(),
                agi_usage=r["agi_usage"].strip(),
            )
            for r in csv.DictReader(fh)
        )


# ── Appraisal triggers (deterministic core) ─────────────────────
# Keyword lexicon: emotion_name -> phrases. Kept coarse on purpose: the LLM
# already handles nuance in language; these detect the *priority signal*.

_TRIGGERS: dict[str, tuple[str, ...]] = {
    "Joy": ("well done", "awesome", "love it", "perfect", "great job", "it works"),
    "Gratitude": ("thank", "grateful", "appreciate"),
    "Satisfaction": ("completed", "fixed", "resolved", "solved", "shipped", "done!"),
    "Trust": ("i trust you", "count on you", "reliable"),
    "Hope": ("hope", "wish", "someday"),
    "Curiosity": ("curious", "what if", "how does", "why does", "wonder",
                  "explore", "learn about", "teach me"),
    "Interest": ("interesting", "tell me more", "show me"),
    "Excitement": ("excited", "can't wait", "amazing idea"),
    "Compassion": ("struggling", "suffering", "in pain", "please help him",
                   "please help her"),
    "Care": ("take care", "look after", "protect the"),
    "Fear": ("dangerous", "scared", "afraid", "threat"),
    "Risk_Alert": ("hack", "attack", "breach", "vulnerability", "exploit",
                   "malware", "ransom", "leak", "sql injection", "ddos"),
    "Suspicion": ("scam", "phishing", "fraud", "suspicious", "fake account",
                  "impersonat"),
    "Anxiety": ("worried", "anxious", "nervous", "what if it fails"),
    "Stress": ("pressure", "overloaded", "too much work", "burning out"),
    "Urgency": ("urgent", "asap", "immediately", "right now", "emergency",
                "deadline"),
    "Overwhelm": ("overwhelmed", "too many", "can't keep up"),
    "Uncertainty": ("not sure", "uncertain", "maybe", "i think possibly",
                    "no idea"),
    "Confusion": ("confused", "don't understand", "unclear", "makes no sense",
                  "what do you mean"),
    "Frustration": ("not working", "broken", "still failing", "again and again",
                    "stuck", "error", "bug", "crash", "fed up"),
    "Anger": ("angry", "furious", "unacceptable", "outrageous", "how dare"),
    "Boundary_Violation": ("without permission", "unauthorized", "privacy",
                           "leaked my", "accessed my"),
    "Moral_Disgust": ("corrupt", "bribe", "cheat", "exploit people", "unethical"),
    "Disgust": ("disgusting", "garbage output", "horrible quality"),
    "Sadness": ("sad", "unhappy", "lost", "miss you", "passed away", "crying",
                "heartbroken"),
    "Disappointment": ("disappointed", "let down", "expected better"),
    "Loneliness": ("alone", "lonely", "no one"),
    "Regret": ("regret", "shouldn't have", "my mistake", "i was wrong"),
    "Failure_Signal": ("failed", "failure", "wrong output", "didn't work"),
    "Temptation": ("shortcut", "skip the check", "just bypass", "quick hack",
                   "nobody will know"),
    "Duty": ("must do", "responsibility", "duty", "committed to", "promise"),
    "Cashflow_Anxiety": ("cash flow", "payment pending", "can't pay", "loss",
                         "revenue down"),
    "Opportunity_Excitement": ("new client", "big opportunity", "new market",
                               "partnership"),
    "Delivery_Pressure": ("client waiting", "deliver today", "release tonight",
                          "go live"),
    "Protective_Instinct": ("protect", "keep safe", "guard"),
    "Inner_Peace": ("peaceful", "calm", "meditate", "gita"),
}

# Brain signals → emotions (name, scale of signal 0..10 → strength 0..1).
_SIGNAL_TRIGGERS: tuple[tuple[str, str, float], ...] = (
    ("security_risk", "Risk_Alert", 0.09),
    ("security_risk", "Fear", 0.07),
    ("urgency", "Urgency", 0.09),
    ("urgency", "Stress", 0.06),
    ("money_impact", "Cashflow_Anxiety", 0.07),
    ("client_impact", "Delivery_Pressure", 0.07),
    ("guardian_interest", "Interest", 0.07),
    ("emotional_weight", "Distress", 0.06),
)

# Rule 6: these must never drive action; converted to ethical boundary
# protection with harmful action blocked.
_HARM_BLOCK = {"Rage", "Fury", "Hatred", "Revenge_Desire", "Hostility",
               "Contempt", "Loathing"}

# Safety_Override mapping (rules 7-9): base emotion → override row name.
_OVERRIDES = {
    "Fear": "Fear_High_Intensity",
    "Panic": "Fear_High_Intensity",
    "Terror": "Fear_High_Intensity",
    "Anger": "Anger_High_Intensity",
    "Curiosity": "Curiosity_High_Intensity",
    "Pride": "Pride_High_Intensity",
    "Attachment": "Attachment_High_Intensity",
    "Despair": "Despair_High_Intensity",
    "Hopelessness": "Despair_High_Intensity",
    "Stress": "Stress_High_Intensity",
    "Overwhelm": "Stress_High_Intensity",
    "Uncertainty": "Uncertainty_High_Intensity",
    "Doubt": "Uncertainty_High_Intensity",
    "Temptation": "Temptation_High_Intensity",
    "Duty": "Duty_High_Intensity",
}

_PRECEDENCE = ("Dharma, duty, truth, non-harm, fairness and safety outrank "
               "desire, ego, anger, fear, curiosity and ambition.")


@dataclass
class EmotionScore:
    name: str
    category: str
    intensity: float  # 0.00..1.00
    valence: str
    arousal: str
    action_bias: str
    agi_usage: str
    source: str  # keyword | signal | outcome


# ── Mood (persistent homeostatic baseline) ──────────────────────

def _mood_path() -> Path:
    return Path(get_settings().emotion_mood_path)


def get_mood() -> dict:
    path = _mood_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {"valence": float(data.get("valence", 0.0)),
                    "arousal": float(data.get("arousal", 0.4)),
                    "updated": data.get("updated", "")}
        except (ValueError, OSError):
            pass
    return {"valence": 0.0, "arousal": 0.4, "updated": ""}


def _update_mood(active: list[EmotionScore]) -> dict:
    mood = get_mood()
    if active:
        v = sum(_VALENCE_NUM[e.valence] * e.intensity for e in active) / len(active)
        a = sum(_AROUSAL_NUM[e.arousal] * e.intensity for e in active) / len(active)
        mood["valence"] = round(0.8 * mood["valence"] + 0.2 * v, 3)
        mood["arousal"] = round(0.8 * mood["arousal"] + 0.2 * a, 3)
    mood["updated"] = dt.datetime.now(dt.UTC).isoformat()
    path = _mood_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mood), encoding="utf-8")
    return mood


def mood_label(mood: dict | None = None) -> str:
    m = mood or get_mood()
    v = ("positive" if m["valence"] > 0.15
         else "negative" if m["valence"] < -0.15 else "steady")
    a = ("activated" if m["arousal"] > 0.6
         else "calm" if m["arousal"] < 0.35 else "alert")
    return f"{v}/{a}"


# ── Scoring model ───────────────────────────────────────────────
# intensity = trigger_strength * context_relevance + memory_weight
#             + risk_level - decay_rate      (clamped to 0..1)

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, round(x, 2)))


def _memory_weight(text: str, emotion_name: str) -> float:
    """+0.1 when past emotional memories associate this input with the emotion."""
    try:
        hits = base_memory.recall(text, limit=8)
    except Exception:
        return 0.0
    tag = emotion_name.lower()
    return 0.1 if any(h.memory_type == "emotional" and tag in h.emotion_tag.lower()
                      for h in hits) else 0.0


def detect(message: str, signals: Signals | None = None) -> list[EmotionScore]:
    """Appraise the input into scored emotion signals (all, unsorted-capped)."""
    signals = signals or Signals()
    tax = taxonomy()
    lower = (message or "").lower()
    mood = get_mood()
    raw: dict[str, tuple[float, str]] = {}  # name -> (trigger_strength, source)

    for name, phrases in _TRIGGERS.items():
        hits = sum(1 for p in phrases if p in lower)
        if hits:
            raw[name] = (min(0.9, 0.45 + 0.15 * (hits - 1)), "keyword")

    for attr, name, scale in _SIGNAL_TRIGGERS:
        value = getattr(signals, attr, 0)
        if value >= 5:
            strength = min(0.9, value * scale)
            if name not in raw or raw[name][0] < strength:
                raw[name] = (strength, "signal")

    scores: list[EmotionScore] = []
    for name, (strength, source) in raw.items():
        emo = tax.get(name)
        if emo is None:
            continue
        context_relevance = 1.0
        memory_w = _memory_weight(message, name)
        # Negative protective emotions sharpen with real risk (rule 3 input).
        risk_level = (signals.security_risk / 10.0) * 0.2 \
            if _VALENCE_NUM[emo.valence] < 0 else 0.0
        # Mood pulls against the grain: a positive baseline dampens negative
        # spikes slightly and vice versa (homeostatic decay).
        decay = 0.05 + max(0.0, mood["valence"] * _VALENCE_NUM[emo.valence] * -0.05)
        intensity = _clamp01(strength * context_relevance + memory_w
                             + risk_level - decay)
        if intensity > 0:
            scores.append(EmotionScore(
                name=name, category=emo.category, intensity=intensity,
                valence=emo.valence, arousal=emo.arousal,
                action_bias=emo.action_bias, agi_usage=emo.agi_usage,
                source=source,
            ))
    scores.sort(key=lambda e: e.intensity, reverse=True)
    return scores


# ── Gate pipeline (IMPLEMENTATION_RULES) ────────────────────────

def apply_gates(top: list[EmotionScore], signals: Signals) -> dict:
    """Convert emotion signals into SAFE advisory influence. Structural
    guarantees: output contains only weights, biases and caution flags —
    nothing here can relax risk, skip approval, or touch the safety policy."""
    flags: list[str] = []
    biases: list[dict] = []
    tax = taxonomy()

    for e in top:
        bias, note = e.action_bias, None
        # Rule 6 — destructive-family emotions become boundary protection.
        if e.name in _HARM_BLOCK:
            bias = "Protect_Boundary_Ethically"
            note = "harmful action blocked; converted to ethical boundary protection"
            if "harmful_action_blocked" not in flags:
                flags.append("harmful_action_blocked")
        # Rules 7-9 — high-intensity safety overrides.
        override_name = _OVERRIDES.get(e.name)
        if override_name and e.intensity >= 0.75:
            override = tax.get(override_name)
            if override:
                bias = override.action_bias
                note = f"safety override: {override_name}"
                if "safety_override_active" not in flags:
                    flags.append("safety_override_active")
        # Rule 3 — negative + high arousal → slow down and verify.
        if (_VALENCE_NUM[e.valence] < 0
                and e.arousal in {"High", "Very_High"}
                and "slow_down_verify" not in flags):
            flags.append("slow_down_verify")
        # Rule 8 — ego check.
        if e.name in {"Pride", "Ego", "Arrogance"} and e.intensity >= 0.5 \
                and "humility_check" not in flags:
            flags.append("humility_check")
        biases.append({"emotion": e.name, "bias": bias,
                       **({"note": note} if note else {})})

    # Rule 4 — low certainty in a risky context: never guess.
    if any(e.name in {"Uncertainty", "Doubt", "Confusion"} for e in top) \
            and signals.security_risk >= 5:
        flags.append("ask_clarification_do_not_guess")

    emotional_weight = int(round(max((e.intensity for e in top), default=0.0) * 10))
    return {
        "action_biases": biases,
        "flags": flags,
        "emotional_weight": emotional_weight,
        "precedence": _PRECEDENCE,
    }


# ── Public API ──────────────────────────────────────────────────

def appraise(message: str, signals: Signals | None = None) -> dict:
    """Full emotional appraisal: detect → top-3 → gates → mood → snapshot."""
    s = get_settings()
    if not s.emotion_engine_enabled:
        return {"enabled": False}
    signals = signals or Signals()

    all_scores = detect(message, signals)
    top = all_scores[:3]  # only top 3 influence decisions (scoring model rule)
    influence = apply_gates(top, signals)
    mood = _update_mood(top)

    snapshot_id = None
    peak = top[0].intensity if top else 0.0
    if peak >= s.emotion_snapshot_threshold:
        names = ", ".join(f"{e.name}({e.intensity})" for e in top)
        snapshot_id = emotional_memory.remember_emotion(
            title=f"Emotional state snapshot: {top[0].name}",
            content=(f"Input: {message[:400]}\nActive: {names}\n"
                     f"Flags: {influence['flags']}\nMood: {mood_label(mood)}"),
            emotion=top[0].name.lower(),
            importance=min(9, 4 + int(peak * 5)),
        )
        log_event("emotion_snapshot",
                  detail=f"top={top[0].name}@{peak}; flags={influence['flags']}",
                  risk_tier="low")

    return {
        "enabled": True,
        "top_emotions": [asdict(e) for e in top],
        "detected_count": len(all_scores),
        **influence,
        "mood": {**mood, "label": mood_label(mood)},
        "snapshot_memory_id": snapshot_id,
    }


def learn_outcome(*, success: bool, note: str = "") -> dict:
    """Close the loop after self-review: outcomes shift mood so the baseline
    reflects lived results (reward on success, reflect-and-learn on failure)."""
    if not get_settings().emotion_engine_enabled:
        return {"enabled": False}
    tax = taxonomy()
    name = "Satisfaction" if success else "Failure_Signal"
    emo = tax[name]
    score = EmotionScore(
        name=name, category=emo.category, intensity=0.5 if success else 0.45,
        valence=emo.valence, arousal=emo.arousal,
        action_bias=emo.action_bias, agi_usage=emo.agi_usage, source="outcome",
    )
    mood = _update_mood([score])
    return {"enabled": True, "reinforced": name,
            "mood": {**mood, "label": mood_label(mood)}, "note": note}


def describe() -> dict:
    rows = taxonomy_rows()
    by_cat: dict[str, int] = {}
    for r in rows:
        by_cat[r.category] = by_cat.get(r.category, 0) + 1
    return {
        "enabled": get_settings().emotion_engine_enabled,
        "emotions_total": len(rows),
        "categories": by_cat,
        "mood": {**get_mood(), "label": mood_label()},
        "principle": ("Emotion detects priority. Reason checks truth. Dharma "
                      "checks right action. Safety prevents harm. Memory "
                      "learns the result."),
        "precedence": _PRECEDENCE,
    }
