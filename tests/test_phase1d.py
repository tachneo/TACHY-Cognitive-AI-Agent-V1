"""Phase 1D — TODY outbound actions are approval-gated (no live network).

Verifies the safety guardrail: send/post never fire without an approved approval.
The live TODY connection itself is checked out-of-band (not in the hermetic suite).
"""


def test_send_is_high_risk():
    from app.safety.policy import RiskTier, classify
    assert classify("send_message") is RiskTier.HIGH
    assert classify("create_post") is RiskTier.HIGH


def test_request_send_only_queues(monkeypatch):
    from app.agents import tody_agent
    out = tody_agent.request_send(123, "hello world")
    assert out["queued"] is True
    assert out["approval"]["status"] == "pending"
    assert out["approval"]["risk_tier"] == "high"


def test_execute_send_blocked_until_approved(monkeypatch):
    from app.agents import tody_agent

    # Guard against any real network call — must never reach the client here.
    def _boom(*a, **k):
        raise AssertionError("send_message must not be called before approval")
    monkeypatch.setattr(tody_agent.get_client().__class__, "send_message", _boom)

    q = tody_agent.request_send(123, "hi")
    aid = q["approval"]["id"]

    # While pending → blocked
    res = tody_agent.execute_send(aid, 123, "hi")
    assert res["sent"] is False
    assert "pending" in res["reason"]

    # Rejected → still blocked
    from app.safety import approvals
    approvals.respond(aid, approved=False)
    res2 = tody_agent.execute_send(aid, 123, "hi")
    assert res2["sent"] is False
    assert "not approved" in res2["reason"]
