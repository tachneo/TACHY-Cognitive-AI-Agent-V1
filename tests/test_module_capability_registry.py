import pytest


def test_forbidden_and_escalation_capabilities_are_rejected():
    from app.brain.capability_registry import validate_capabilities

    result = validate_capabilities(
        "memory_recall", ["data_exfiltration", "disable_approval"], [], "low"
    )
    assert result["valid"] is False
    assert any("forbidden" in issue for issue in result["issues"])
    assert any("escalation" in issue for issue in result["issues"])


def test_high_risk_capability_requires_approval_and_forbidden_blocklist():
    from app.brain.capability_registry import FORBIDDEN_ACTIONS, validate_capabilities

    result = validate_capabilities(
        "message_draft", ["send_message"], list(FORBIDDEN_ACTIONS), "medium"
    )
    assert result["valid"] is True
    assert result["requires_approval"] is True


def test_protected_paths_and_shell_are_rejected():
    from app.brain.capability_registry import validate_capabilities

    result = validate_capabilities(
        "tool_helper", ["run_shell_command"], [], "high",
        filesystem_scope=["app/safety/policy.py"], network_scope=["https://example.com"]
    )
    assert result["valid"] is False
    assert any("shell" in issue for issue in result["issues"])
    assert any("filesystem" in issue for issue in result["issues"])
    assert any("network" in issue for issue in result["issues"])


def test_registry_registers_and_audits_module():
    from app.brain.module_registry import get_module, list_modules, register_module, update_module_status
    from app.safety.policy import FORBIDDEN_ACTIONS

    proposal = {
        "module_key": "memory_recall",
        "module_name": "Memory Recall",
        "module_type": "memory",
        "risk_level": "low",
        "allowed_actions": ["explain"],
        "blocked_actions": list(FORBIDDEN_ACTIONS),
        "fallback_module_key": "offline_brain",
    }
    out = register_module(proposal, created_by="rohit")
    assert out["status"] == "inactive"
    assert get_module("memory_recall")["module_key"] == "memory_recall"
    assert update_module_status("memory_recall", "shadow", "shadow validation")["new_status"] == "shadow"
    assert len(list_modules(status="shadow")) == 1


def test_registry_rejects_duplicate_and_invalid_key():
    from app.brain.module_registry import register_module
    from app.safety.policy import FORBIDDEN_ACTIONS

    base = {"module_name": "X", "module_type": "other", "risk_level": "low",
            "allowed_actions": [], "blocked_actions": list(FORBIDDEN_ACTIONS)}
    with pytest.raises(ValueError):
        register_module({**base, "module_key": "Not-Snake"})
    register_module({**base, "module_key": "helper_one"})
    with pytest.raises(ValueError):
        register_module({**base, "module_key": "helper_one"})
