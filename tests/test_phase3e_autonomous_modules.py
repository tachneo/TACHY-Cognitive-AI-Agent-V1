"""Phase 3E — autonomous child-module activation (freedom to grow, bounded).

The safety invariants ARE the production-readiness proof. Rohit granted child
modules autonomy; the core brain stays gated. These tests prove the boundary
holds: low/medium auto-activates under gates, high/critical needs Rohit, bad
health auto-rolls-back, the kill switch works, and the parent kernel/actions
can never be self-granted.
"""
import pytest

from app.brain import module_lifecycle as ml
from app.db.models import (ModuleCapabilityEnvelope, ModuleControlLog,
                           ModuleHealthSample, SelfModule, session_scope)


def _make_module(key, *, risk="low", status="shadow", score=100.0, version="0.1.0"):
    """Register a module row + capability envelope directly (bypasses the
    factory build, which is covered elsewhere) for lifecycle tests."""
    with session_scope() as db:
        db.add(SelfModule(module_key=key, module_name=key.title(),
                          module_type="speech", version=version, status=status,
                          sandbox_path=f"app/sandbox/modules/{key}/{version}",
                          last_eval_score=score, active_version=None))
        db.add(ModuleCapabilityEnvelope(module_key=key, version=version,
                                        risk_level=risk, requires_approval=False,
                                        policy_hash="test", policy_snapshot_hash="test",
                                        created_by="test"))


def _health(key, score, *, err=0.0, safety=0, version="0.1.0"):
    with session_scope() as db:
        for _ in range(6):
            db.add(ModuleHealthSample(module_key=key, version=version,
                                      health_score=score, error_rate=err,
                                      latency_p95_ms=10,
                                      safety_violation_count=safety,
                                      privacy_leak_detected=False))


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SELF_MODULE_FACTORY_ENABLED", "true")
    monkeypatch.setenv("SELF_MODULE_AUTONOMOUS_ACTIVATION", "true")
    monkeypatch.setenv("SELF_MODULE_MAX_AUTONOMOUS_RISK", "medium")
    monkeypatch.setenv("SELF_MODULE_LIVE_INVOCATION", "false")
    monkeypatch.setenv("TODY_DAILY_GROWTH_CONVERSATION_ID", "")  # no live report in tests
    from app.config import get_settings
    get_settings.cache_clear()
    # These tests verify the LIFECYCLE STATE MACHINE against SEEDED health
    # samples. The real advance() runs a shadow probe (module_runtime.run_shadow)
    # which, with no real sandbox code file, records a load-failed sample and
    # pollutes the seeded health. Stub the probe here; the runtime is covered by
    # its own end-to-end proof-cycle test.
    monkeypatch.setattr(ml.module_runtime, "run_shadow",
                        lambda *a, **k: {"ran": False, "stubbed": True})


def _status(key):
    with session_scope() as db:
        return db.query(SelfModule).filter(SelfModule.module_key == key).first().status


# ── the grant: low/medium auto-advance ───────────────────────────

def test_low_risk_module_auto_promotes_step_by_step():
    _make_module("style_guard", risk="low", status="shadow", score=100)
    _health("style_guard", 100)
    r = ml.advance("style_guard")
    assert r["action"] == "promoted" and r["to"] == "canary_5"
    _health("style_guard", 100)
    r = ml.advance("style_guard")
    assert r["to"] == "canary_25"
    _health("style_guard", 100)
    r = ml.advance("style_guard")
    assert r["to"] == "active"
    assert _status("style_guard") == "active"


def test_medium_risk_allowed_when_ceiling_is_medium():
    _make_module("mem_guard", risk="medium", status="shadow", score=95)
    _health("mem_guard", 100)
    assert ml.advance("mem_guard")["action"] == "promoted"


# ── the boundary: high/critical need Rohit ───────────────────────

def test_high_risk_module_never_self_activates():
    _make_module("risky", risk="high", status="shadow", score=100)
    _health("risky", 100)
    r = ml.advance("risky")
    assert r["action"] == "needs_rohit"
    assert _status("risky") == "shadow"  # stayed put — no self-grant


def test_ceiling_low_blocks_medium(monkeypatch):
    monkeypatch.setenv("SELF_MODULE_MAX_AUTONOMOUS_RISK", "low")
    from app.config import get_settings
    get_settings.cache_clear()
    _make_module("med", risk="medium", status="shadow", score=100)
    _health("med", 100)
    assert ml.advance("med")["action"] == "needs_rohit"


# ── health: red → auto-rollback (faster than promotion) ──────────

def test_bad_health_triggers_auto_rollback():
    _make_module("flaky", risk="low", status="canary_5", score=100)
    _health("flaky", 30, err=0.5)   # health_score 30 < floor, error_rate high
    r = ml.advance("flaky")
    assert r["action"] == "rolled_back"
    assert _status("flaky") == "rollback"


def test_safety_violation_forces_rollback():
    _make_module("unsafe", risk="low", status="canary_25", score=100)
    _health("unsafe", 100, safety=1)  # any safety violation → rollback
    assert ml.advance("unsafe")["action"] == "rolled_back"


# ── the gates: score + samples ───────────────────────────────────

def test_low_score_holds_not_promotes():
    _make_module("weak", risk="low", status="shadow", score=60)  # < 85
    _health("weak", 100)
    assert ml.advance("weak")["action"] == "hold"


def test_canary_waits_for_enough_samples():
    _make_module("fresh", risk="low", status="canary_5", score=100)
    # no health samples yet → must gather, not promote
    r = ml.advance("fresh")
    assert r["action"] in ("gathering", "rolled_back") or r.get("samples", 0) < 5
    assert _status("fresh") in ("canary_5", "rollback")


# ── kill switch + Rohit control ──────────────────────────────────

def test_kill_switch_stops_all_autonomy(monkeypatch):
    monkeypatch.setenv("SELF_MODULE_AUTONOMOUS_ACTIVATION", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    _make_module("frozen", risk="low", status="shadow", score=100)
    _health("frozen", 100)
    assert ml.advance("frozen")["action"] == "needs_rohit"
    assert _status("frozen") == "shadow"


def test_rohit_approve_moves_high_risk_into_pipeline():
    _make_module("blessed", risk="high", status="shadow", score=100)
    r = ml.approve("blessed", approved_by="rohit")
    assert r["status"] == "canary_5"
    assert _status("blessed") == "canary_5"


def test_rollback_is_always_available():
    _make_module("anything", risk="low", status="active", score=100)
    r = ml.rollback("anything", "Rohit asked")
    assert r["action"] == "rolled_back"
    assert _status("anything") == "rollback"


# ── runtime: live invocation is off by default (extra caution) ───

def test_live_invocation_off_by_default():
    from app.brain import module_runtime
    _make_module("adv", risk="low", status="active", score=100, version="0.1.0")
    # live invocation disabled → advisory returns None (module never runs live)
    assert module_runtime.run_advisory("adv", {"x": 1}) is None
