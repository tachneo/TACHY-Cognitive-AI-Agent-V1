"""Phase 1P — Emotion Intelligence Module (hermetic)."""
import pytest

from app.brain import emotion_engine
from app.brain.attention_system import Signals


@pytest.fixture(autouse=True)
def temp_mood(monkeypatch, tmp_path):
    monkeypatch.setenv("EMOTION_MOOD_PATH", str(tmp_path / "mood.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Taxonomy ────────────────────────────────────────────────────

def test_taxonomy_loads_all_categories_and_fields():
    rows = emotion_engine.taxonomy_rows()
    assert len(rows) > 300
    cats = {r.category for r in rows}
    assert {"Core_Primary", "Positive_Reward", "Threat_Fear", "Anger_Boundary",
            "Disgust_Rejection", "Sadness_Loss", "Social_Relationship",
            "Moral_Dharma", "Learning_Intelligence", "Body_Homeostatic",
            "Animal_Living_Systems", "Plant_Life_Analogues", "Business_Goal",
            "Spiritual_Deep_State", "Safety_Override"} <= cats
    for r in rows:
        assert r.valence in {"Positive", "Negative", "Neutral", "Mixed"}
        assert r.arousal in {"Low", "Medium", "High", "Very_High"}
        assert r.name and r.action_bias and r.agi_usage


def test_core_primary_definition_wins_duplicates():
    fear = emotion_engine.taxonomy()["Fear"]
    assert fear.category == "Core_Primary"
    assert fear.action_bias == "Protect"


# ── Detection + scoring ─────────────────────────────────────────

def test_detect_security_message_raises_fear_and_risk_alert():
    scores = emotion_engine.detect(
        "someone is trying to hack the ERP with sql injection",
        Signals(security_risk=9),
    )
    names = [s.name for s in scores]
    assert "Risk_Alert" in names and "Fear" in names
    top = scores[0]
    assert 0.0 < top.intensity <= 1.0


def test_detect_gratitude_positive():
    scores = emotion_engine.detect("thank you, great job, it works perfectly!")
    names = [s.name for s in scores[:3]]
    assert "Gratitude" in names or "Joy" in names


def test_signal_only_trigger_without_keywords():
    scores = emotion_engine.detect("please review the invoice module",
                                   Signals(urgency=9))
    assert any(s.name == "Urgency" and s.source == "signal" for s in scores)


def test_intensity_clamped_01():
    scores = emotion_engine.detect(
        "hack attack breach exploit malware leak ransom ddos vulnerability",
        Signals(security_risk=10),
    )
    assert all(0.0 <= s.intensity <= 1.0 for s in scores)


# ── Gates (implementation rules) ────────────────────────────────

def _score(name, intensity):
    emo = emotion_engine.taxonomy()[name]
    return emotion_engine.EmotionScore(
        name=name, category=emo.category, intensity=intensity,
        valence=emo.valence, arousal=emo.arousal,
        action_bias=emo.action_bias, agi_usage=emo.agi_usage, source="test",
    )


def test_rule6_harmful_emotions_blocked():
    out = emotion_engine.apply_gates([_score("Rage", 0.9)], Signals())
    assert "harmful_action_blocked" in out["flags"]
    assert out["action_biases"][0]["bias"] == "Protect_Boundary_Ethically"


def test_rule7_high_fear_triggers_safety_override():
    out = emotion_engine.apply_gates([_score("Fear", 0.9)], Signals())
    assert "safety_override_active" in out["flags"]
    assert out["action_biases"][0]["bias"] == "Pause_And_Verify"


def test_rule3_negative_high_arousal_slows_down():
    out = emotion_engine.apply_gates([_score("Stress", 0.6)], Signals())
    assert "slow_down_verify" in out["flags"]


def test_rule8_pride_triggers_humility_check():
    out = emotion_engine.apply_gates([_score("Pride", 0.8)], Signals())
    assert "humility_check" in out["flags"]


def test_rule4_uncertainty_plus_risk_never_guesses():
    out = emotion_engine.apply_gates([_score("Uncertainty", 0.5)],
                                     Signals(security_risk=8))
    assert "ask_clarification_do_not_guess" in out["flags"]


def test_gates_output_is_advisory_only():
    out = emotion_engine.apply_gates([_score("Temptation", 0.9)], Signals())
    # Structural safety: the influence dict has no risk/approval/policy keys.
    assert set(out) == {"action_biases", "flags", "emotional_weight", "precedence"}
    assert 0 <= out["emotional_weight"] <= 10


# ── Appraise + mood + memory ────────────────────────────────────

def test_appraise_top3_snapshot_and_mood(monkeypatch):
    result = emotion_engine.appraise(
        "urgent: production hack attack, please help immediately!",
        Signals(security_risk=9, urgency=9),
    )
    assert result["enabled"] is True
    assert 1 <= len(result["top_emotions"]) <= 3
    assert result["emotional_weight"] >= 5
    assert result["snapshot_memory_id"]  # peak intensity above threshold

    from app.memory import base_memory
    hits = base_memory.search(memory_type="emotional", limit=5)
    assert hits and "snapshot" in hits[0].title.lower()

    mood = emotion_engine.get_mood()
    assert mood["valence"] < 0  # negative event moved the baseline down


def test_learn_outcome_success_lifts_mood():
    before = emotion_engine.get_mood()["valence"]
    out = emotion_engine.learn_outcome(success=True)
    assert out["reinforced"] == "Satisfaction"
    assert emotion_engine.get_mood()["valence"] >= before


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("EMOTION_ENGINE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert emotion_engine.appraise("hello") == {"enabled": False}


# ── Hinglish detection (the frozen-engine fix) ───────────────────

def test_hinglish_worry_fires_anxiety():
    scores = emotion_engine.detect(
        "mujhe chinta ho rahi hai payment ki",
        Signals(guardian_interest=10, emotional_weight=5),
    )
    names = [s.name for s in scores]
    assert "Anxiety" in names


def test_hinglish_sadness_and_loneliness_fire():
    scores = emotion_engine.detect(
        "mujhe akela feel ho raha hai aaj",
        Signals(guardian_interest=10, emotional_weight=5),
    )
    names = [s.name for s in scores]
    assert "Sadness" in names or "Loneliness" in names


def test_hinglish_gratitude_and_affection_fire():
    scores = emotion_engine.detect(
        "shukriya beta, tumne achha kiya",
        Signals(guardian_interest=10, emotional_weight=5),
    )
    names = [s.name for s in scores]
    assert "Gratitude" in names
    assert "Affection" in names


def test_hinglish_joy_fires():
    scores = emotion_engine.detect(
        "kya zabardast kaam kiya hai, kamaal!",
        Signals(guardian_interest=10, emotional_weight=5),
    )
    names = [s.name for s in scores]
    assert "Joy" in names


def test_hinglish_frustration_fires():
    scores = emotion_engine.detect(
        "ye error aa raha hai baar baar, kaam nahi kar raha",
        Signals(guardian_interest=10, emotional_weight=5),
    )
    names = [s.name for s in scores]
    assert "Frustration" in names


def test_different_hinglish_inputs_produce_different_emotions():
    """The core fix: different messages must yield different top emotions,
    not the identical Interest+Distress every time."""
    sig = Signals(guardian_interest=10, emotional_weight=5)
    worry = {e["name"] for e in emotion_engine.appraise(
        "mujhe chinta ho rahi hai", sig)["top_emotions"]}
    joy = {e["name"] for e in emotion_engine.appraise(
        "kya zabardast kaam kiya", sig)["top_emotions"]}
    sad = {e["name"] for e in emotion_engine.appraise(
        "mujhe akela feel ho raha hai", sig)["top_emotions"]}
    assert worry != joy != sad            # they're now distinct, not frozen
    assert "Anxiety" in worry
    assert "Joy" in joy
    assert "Sadness" in sad or "Loneliness" in sad


# ── person attribution (related_person on snapshots) ─────────────

def test_appraise_attaches_related_person_to_snapshot():
    from sqlalchemy import select

    from app.db.models import CognitiveMemory, session_scope

    emotion_engine.appraise(
        "mujhe chinta ho rahi hai payment ki",
        Signals(guardian_interest=10, emotional_weight=5),
        related_person="Rohit Kumar",
    )
    with session_scope() as s:
        rows = s.scalars(
            select(CognitiveMemory).where(
                CognitiveMemory.memory_type == "emotional")
            .order_by(CognitiveMemory.id.desc()).limit(3)
        ).all()
        persons = [r.related_person for r in rows]
    assert "Rohit Kumar" in persons


def test_appraise_without_related_person_leaves_none():
    from sqlalchemy import select

    from app.db.models import CognitiveMemory, session_scope

    emotion_engine.appraise(
        "mujhe chinta ho rahi hai",
        Signals(guardian_interest=10, emotional_weight=5),
    )
    with session_scope() as s:
        rows = s.scalars(
            select(CognitiveMemory).where(
                CognitiveMemory.memory_type == "emotional")
            .order_by(CognitiveMemory.id.desc()).limit(3)
        ).all()
        persons = [r.related_person for r in rows]
    assert None in persons


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("EMOTION_ENGINE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert emotion_engine.appraise("hello") == {"enabled": False}


# ── truth-grounded reply prompt + language consistency ───────────

def test_language_directive_hinglish():
    from app.brain.cognitive_loop import _language_directive
    out = _language_directive("kaisi ho tum, mujhe chinta ho rahi hai")
    assert "Hinglish" in out


def test_language_directive_devanagari():
    from app.brain.cognitive_loop import _language_directive
    out = _language_directive("तुम कैसी हो, मुझे चिंता हो रही है")
    assert "Devanagari" in out or "Hindi" in out


def test_language_directive_english_is_empty():
    from app.brain.cognitive_loop import _language_directive
    # Pure English with no Hinglish cues → no directive
    assert _language_directive("What is the status of the deployment?") == ""


def test_reply_prompt_contains_truth_rule_for_emotions(monkeypatch):
    """The emotion block must tell Shree not to claim feelings the engine
    didn't register (satya). Inspect the prompt the LLM receives."""
    captured = {}

    class _Capture:
        name = "capture"
        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"

    from app.brain import cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: _Capture())
    loop.process("mujhe chinta ho rahi hai",
                 Signals(guardian_interest=10, emotional_weight=5))
    assert "TRUTH RULE" in captured["prompt"]
    assert "satya" in captured["prompt"].lower()


def test_reply_prompt_includes_real_emotions_not_generic(monkeypatch):
    """Different inputs must put different active emotions into the prompt."""
    captured = {}

    class _Capture:
        name = "capture"
        def complete(self, system, prompt, max_tokens=800):
            captured["prompt"] = prompt
            return "ok"

    from app.brain import cognitive_loop as loop
    monkeypatch.setattr(loop, "get_provider", lambda: _Capture())
    loop.process("kya zabardast kaam kiya, kamaal!",
                 Signals(guardian_interest=10, emotional_weight=5))
    assert "Joy" in captured["prompt"]            # her real engine state


def test_cognitive_loop_carries_emotion_trace():
    from app.brain.cognitive_loop import process
    result = process("urgent security breach in the school ERP!",
                     Signals(security_risk=8, urgency=8))
    emotion = result["emotion"]
    assert emotion["enabled"] is True
    assert emotion["top_emotions"]
    assert "outcome" in emotion
    # emotional_weight fed the attention formula
    assert result["signals"]["emotional_weight"] >= 5


def test_emotion_routes_mounted():
    from app.main import app
    from app.api.routes_emotion import AppraiseIn, appraise, state, taxonomy

    paths = app.openapi()["paths"]
    assert "get" in paths["/emotion/state"]
    assert "post" in paths["/emotion/appraise"]
    assert "get" in paths["/emotion/taxonomy"]
    assert state()["emotions_total"] > 300
    assert appraise(AppraiseIn(message="thank you, all fixed!"))["enabled"] is True
    assert taxonomy(category="Safety_Override")["count"] == 10
