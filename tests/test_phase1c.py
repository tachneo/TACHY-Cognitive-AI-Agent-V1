"""Phase 1C — agents, approval workflow, and reflection (isolated temp DB)."""


def test_agent_routing():
    from app.agents.main_agent import route
    assert route("Review this PHP file for SQL injection") == "security"
    assert route("Client wants a lower price, what proposal?") == "business"
    assert route("Fix this python function bug") == "coding"


def test_security_agent_runs_with_checklist():
    from app.agents.main_agent import handle
    res = handle("Review this ERP endpoint for security", agent="security")
    assert res.agent == "security"
    assert res.reply  # heuristic provider still returns text
    assert res.decision["project"] in {"TACHY_SCHOOL_ERP", "GENERAL"}


def test_approval_workflow_roundtrip():
    from app.safety import approvals
    req = approvals.request_approval("production_deploy", payload="fees module v2")
    assert req["risk_tier"] == "high"
    assert req["status"] == "pending"
    pending = approvals.list_pending()
    assert any(p["id"] == req["id"] for p in pending)
    done = approvals.respond(req["id"], approved=True)
    assert done["status"] == "approved"
    # second response is a no-op
    again = approvals.respond(req["id"], approved=False)
    assert again["status"] == "approved"


def test_daily_reflection():
    from app.brain.learning_engine import daily_reflection
    from app.memory import base_memory
    base_memory.add(memory_type="failure", title="Scope creep again",
                    content="client repeated change requests", project="ERP_CRM_AI")
    out = daily_reflection()
    assert out["saved"] is True
    assert "Reviewed" in out["summary"]
