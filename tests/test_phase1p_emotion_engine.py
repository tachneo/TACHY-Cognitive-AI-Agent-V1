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
    assert emotion_engine.learn_outcome(success=True) == {"enabled": False}


# ── Cognitive loop integration + routes ─────────────────────────

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
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        state = client.get("/emotion/state")
        assert state.status_code == 200
        assert state.json()["emotions_total"] > 300

        appraise = client.post("/emotion/appraise",
                               json={"message": "thank you, all fixed!"})
        assert appraise.status_code == 200
        assert appraise.json()["enabled"] is True

        tax = client.get("/emotion/taxonomy",
                         params={"category": "Safety_Override"})
        assert tax.status_code == 200
        assert tax.json()["count"] == 10
