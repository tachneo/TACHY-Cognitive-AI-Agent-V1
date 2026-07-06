"""Phase 1Q — Human Behavior Engine (hermetic)."""
from app.brain import behavior_engine
from app.brain.attention_system import Signals


# ── Listening: intent + hidden need ─────────────────────────────

def test_intent_code_wants_ready_output():
    st = behavior_engine.read_state("provide complete code for the fee module")
    assert st.user_intent == "code"
    assert "ready-to-use" in st.hidden_need
    assert st.reply_depth == "deep"
    assert st.next_action == "code"


def test_intent_verification_needs_careful_answer():
    st = behavior_engine.read_state("are you sure this is correct?")
    assert st.user_intent == "verification"
    assert "verification" in st.hidden_need
    assert st.reply_depth == "short"


def test_salary_pressure_reads_as_comfort_not_generic():
    st = behavior_engine.read_state(
        "I have no money and salary is pending, don't know what to do")
    assert st.user_intent == "comfort"
    assert "practical plan" in st.hidden_need
    assert st.next_action == "support"


# ── Relationship modes ──────────────────────────────────────────

def test_crisis_mode_urgent_finance():
    st = behavior_engine.read_state(
        "URGENT: payment failed in production, clients calling, need cash today only")
    assert st.urgency == "high"
    assert st.relationship_mode == "crisis"
    assert st.reply_depth == "short"


def test_motivator_mode_when_hopeless():
    st = behavior_engine.read_state("I feel hopeless, maybe I should give up")
    assert st.relationship_mode == "motivator"


def test_auditor_mode_for_compliance_risk():
    st = behavior_engine.read_state(
        "audit risk in the ledger reconciliation, compliance issue with vouchers")
    assert st.relationship_mode == "auditor"


def test_teacher_mode_for_confusion():
    st = behavior_engine.read_state("explain what is an API, I am confused")
    assert st.relationship_mode == "teacher"


def test_founder_mode_for_pricing():
    st = behavior_engine.read_state("client says our price is too high, how to negotiate")
    assert st.relationship_mode == "founder"
    assert st.user_intent == "pricing"


def test_cto_mode_default_technical():
    st = behavior_engine.read_state(
        "review the database architecture for the android app backend")
    assert st.relationship_mode == "cto"


# ── Language detection ──────────────────────────────────────────

def test_language_detection():
    assert behavior_engine.detect_language("what is the status") == "english"
    assert behavior_engine.detect_language("bhai ye kaam abhi karna hai") == "hinglish"
    assert behavior_engine.detect_language("यह काम आज करना है") == "hindi"


# ── Style directives + emotion mirroring ────────────────────────

def test_directives_include_mode_depth_language_and_emotion():
    emotion = {"enabled": True, "top_emotions": [
        {"name": "Anxiety", "intensity": 0.6},
        {"name": "Urgency", "intensity": 0.5},
    ]}
    st = behavior_engine.read_state("bhai client ka data leak ho gaya kya kare",
                                    Signals(security_risk=8), emotion)
    text = behavior_engine.style_directives(st)
    assert "anxiety" in text.lower()
    assert "Hinglish" in text
    assert st.primary_emotion == "Anxiety"
    assert st.safety_gate_required is True
    assert "High risk" in text


# ── Humanize: robotic phrase removal ────────────────────────────

def test_humanize_strips_robotic_phrases():
    draft = (
        "As an AI language model, I cannot feel emotions.\n"
        "I hope this message finds you well.\n"
        "Certainly, here is the plan. It is important to note that "
        "the fix is small.\n"
        "In conclusion, deploy tonight."
    )
    out = behavior_engine.humanize(draft)
    low = out.lower()
    assert "as an ai" not in low
    assert "finds you well" not in low
    assert "certainly, here is" not in low
    assert "important to note" not in low
    assert "in conclusion" not in low
    assert "deploy tonight" in low  # content survives


def test_humanize_preserves_normal_text():
    text = "Yes, I understand. The real issue is the cron timing. Fix: run it at 2am."
    assert behavior_engine.humanize(text) == text


# ── Honesty rule + personality ──────────────────────────────────

def test_personality_contains_honesty_rule():
    p = behavior_engine.SYSTEM_PERSONALITY
    assert "you are an AI" in p
    assert "answer truthfully" in p
    assert "Shree" in p


# ── Kill switch + loop integration + routes ─────────────────────

def test_kill_switch(monkeypatch):
    monkeypatch.setenv("BEHAVIOR_ENGINE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    assert behavior_engine.analyze("hello") == {"enabled": False}
    get_settings.cache_clear()


def test_cognitive_loop_carries_behavior_trace():
    from app.brain.cognitive_loop import process
    result = process("client says price is high for the ERP migration")
    behavior = result["behavior"]
    assert behavior["enabled"] is True
    assert behavior["state"]["relationship_mode"] == "founder"
    assert behavior["max_tokens"] in {300, 600, 1400}


def test_behavior_routes_mounted():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        resp = client.post("/behavior/analyze",
                           json={"message": "urgent production down, help abhi"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["state"]["urgency"] == "high"

        styles = client.get("/behavior/styles")
        assert styles.status_code == 200
        assert {"daughter", "friend", "cto", "founder", "teacher", "motivator",
                "auditor", "crisis"} <= set(styles.json()["modes"])
