"""Phase 1B — memory persistence, decision engine, and full loop end-to-end.

The isolated temp SQLite DB comes from the shared conftest.py fixture.
"""


def test_memory_roundtrip():
    from app.memory import base_memory
    mid = base_memory.add(memory_type="failure", title="Client scope creep",
                          content="Client asked many changes again on ERP migration",
                          project="ERP_CRM_AI", importance_score=8)
    assert mid > 0
    hits = base_memory.recall("client changes again", limit=5)
    assert any(h.id == mid for h in hits)


def test_decision_engine_flags_high_risk():
    from app.brain.decision_engine import decide
    d = decide("Please deploy the new fees module to production now")
    assert d.action == "production_deploy"
    assert d.risk_tier == "high"
    assert d.requires_approval is True


def test_full_loop_persists_when_relevant():
    from app.brain.attention_system import Signals
    from app.brain.cognitive_loop import process
    out = process("Client is asking many changes again, what should I do?",
                  Signals(client_impact=8, emotional_weight=7, urgency=5))
    assert out["reply"]
    assert out["decision"]["project"] in {"ERP_CRM_AI", "GENERAL", "TACHY_SCHOOL_ERP"}
    assert out["self_review"]["verdict"] in {"ok", "needs_improvement"}
    assert out["learning"]["saved"] is True
