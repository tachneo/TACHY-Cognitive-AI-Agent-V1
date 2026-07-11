def test_factory_generates_and_validates_only_in_sandbox():
    from app.brain.self_module_factory import create_spec, generate_module_code, generate_tests, validate_module
    from app.db.models import SelfModuleProposal, session_scope
    from app.safety.policy import FORBIDDEN_ACTIONS
    import json
    with session_scope() as db:
        p = SelfModuleProposal(module_key="recall_guard", module_name="Recall Guard", module_type="memory", purpose="test", weakness_detected="observed failure", expected_improvement="better recall", proposed_by="rohit", risk_level="low", allowed_actions_json='["explain"]', blocked_actions_json=json.dumps(list(FORBIDDEN_ACTIONS)), required_tests_json='["unit"]', fallback_module_key="offline_brain", rollback_plan="restore")
        db.add(p); db.flush(); pid = p.id
    assert "sandbox" in create_spec(pid)
    assert "sandbox" in generate_module_code(pid)
    assert "sandbox" in generate_tests(pid)
    report = validate_module(pid)
    assert report["passed"] is True


def test_factory_does_not_propose_without_evidence():
    from app.brain.self_module_factory import detect_and_propose
    assert detect_and_propose() is None
