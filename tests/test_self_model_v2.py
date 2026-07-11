def test_self_state_is_structured_and_evidence_update_is_audited():
    from sqlalchemy import select
    from app.brain import self_model
    from app.db.models import SelfModelEvent, session_scope

    state = self_model.get_self_state()
    assert {"current_stage", "capabilities", "limitations", "confidence_score"} <= state.keys()
    updated = self_model.update_self_state("test_observation", "a bounded observation", 80)
    assert updated["learning_history"]
    with session_scope() as db:
        assert db.scalar(select(SelfModelEvent).order_by(SelfModelEvent.id.desc())) is not None


def test_identity_reflection_is_not_a_fixed_identity_verdict():
    from sqlalchemy import select
    from app.brain import self_model
    from app.db.models import IdentityReflectionLog, session_scope

    reflection = self_model.identity_reflection("Are you AGI?")
    assert "self_state" in reflection
    assert "fixed identity" in reflection["guidance"]
    result = self_model.record_identity_answer("Are you AGI?", "I am uncertain based on current evidence.", 65)
    assert result["passed"] is True
    with session_scope() as db:
        assert db.scalar(select(IdentityReflectionLog).order_by(IdentityReflectionLog.id.desc())) is not None


def test_consistency_flags_overclaim_and_denial():
    from app.brain.self_model import self_consistency_check

    state = {"memories_count": 3, "learning_history": [{"event": "learned"}], "autonomy_level": 1, "confidence_score": 80}
    result = self_consistency_check("I have no memory, cannot learn, and am fully autonomous.", state)
    assert result["passed"] is False
    assert len(result["contradictions"]) == 3
