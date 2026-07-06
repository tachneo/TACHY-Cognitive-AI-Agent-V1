"""Smoke tests — the Phase 1A foundation boots and the priority math holds."""
from app.brain.attention_system import Signals, attention_band, priority_score
from app.brain.cognitive_loop import process
from app.safety.policy import RiskTier, classify


def test_priority_formula():
    s = Signals(security_risk=10, money_impact=5, client_impact=5, urgency=5,
                guardian_interest=5, emotional_weight=5)
    # 10*3 + 5*2 + 5*2 + 5 + 5 + 5 = 65
    assert priority_score(s) == 65
    assert attention_band(65) == "critical"


def test_loop_runs():
    out = process("Client is asking many changes again, what should I do?",
                  Signals(client_impact=8, emotional_weight=7, urgency=5))
    assert out["identity"] == "Shree"
    assert out["guardian"] == "Rohit Kumar"
    assert out["attention_band"] in {"low", "normal", "high", "critical"}


def test_safety_tiers():
    assert classify("explain") is RiskTier.LOW
    assert classify("db_modify") is RiskTier.HIGH
    assert classify("malware") is RiskTier.FORBIDDEN
