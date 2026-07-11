"""Phase 3D — self-evolution loop: noticing → weakness → module → shadow.

The metacognitive loop connected to the module factory. Her repair queue
(noticing) now feeds weakness_detector (evidence), which feeds the factory
(build), which registers in SHADOW (never auto-activates). Two real bugs were
fixed to make this work end-to-end:
  - weakness_detector never read the repair queue (the missing bridge)
  - register_module reads list keys (allowed/blocked_actions) but proposals
    carry JSON columns → the blocklist read empty → fail-closed gate rejected
    every module. register_shadow bridges the shapes.
"""
import pytest


@pytest.fixture(autouse=True)
def _factory_on(monkeypatch):
    monkeypatch.setenv("SELF_MODULE_FACTORY_ENABLED", "true")
    monkeypatch.setenv("SELF_MODULE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("SELF_MODULE_CANARY_ENABLED", "false")
    monkeypatch.setenv("BRAIN_SURGERY_ENABLED", "false")
    monkeypatch.setenv("REPAIR_QUEUE_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()


# ── the bridge: repair queue → weakness evidence ─────────────────

def test_weakness_detector_reads_repair_queue():
    from app.brain import repair_queue, weakness_detector as wd
    # Seed a ready signature (tier-1 guardian correction is ready at once).
    repair_queue.note_failure("reply-too-long", tier=1, guardian=True,
                              fix_class="directive", sample="itna lamba")
    weaknesses = wd.detect_weaknesses(limit=5)
    keys = [w["weakness_key"] for w in weaknesses]
    assert "reply-too-long" in keys
    w = next(w for w in weaknesses if w["weakness_key"] == "reply-too-long")
    assert w["recommended_module_type"] == "speech"  # directive → speech guard
    assert w["evidence"]  # never fabricated — carries the real sample/tier


def test_no_weakness_when_queue_empty():
    from app.brain import weakness_detector as wd
    # Nothing ready → nothing proposed (evidence-only, no fabrication).
    assert wd.detect_weaknesses(limit=5) == []


# ── the full loop, ending safely in shadow ───────────────────────

def test_full_loop_notice_to_shadow():
    from app.brain import repair_queue, self_module_factory as f, module_registry as reg
    repair_queue.note_failure("weak-memory-recall", tier=1, guardian=True,
                              fix_class="memory", sample="forgot the task")

    prop = f.detect_and_propose()
    assert prop is not None and "id" in prop
    pid = prop["id"]

    f.create_spec(pid)
    f.generate_module_code(pid)
    f.generate_tests(pid)
    report = f.validate_module(pid)
    assert report["passed"] is True and report["score"] >= 85

    shadow = f.register_shadow(pid)
    assert shadow["ok"] is True
    assert shadow["status"] == "shadow"
    assert shadow["requires_approval"] is True

    # It is registered but NOT activated — active version stays None.
    mkey = prop["module_key"]
    assert reg.get_module(mkey)["status"] == "shadow"
    assert reg.get_active_version(mkey) is None


def test_register_shadow_refuses_unvalidated():
    from app.brain import repair_queue, self_module_factory as f
    repair_queue.note_failure("slow-response", tier=1, guardian=True,
                              fix_class="config")
    prop = f.detect_and_propose()
    # skip validation → must refuse to register
    r = f.register_shadow(prop["id"])
    assert r["ok"] is False
    assert "not validated" in r["reason"]


def test_register_shadow_refuses_when_factory_disabled(monkeypatch):
    from app.brain import repair_queue, self_module_factory as f
    repair_queue.note_failure("false-confidence", tier=1, guardian=True,
                              fix_class="directive")
    prop = f.detect_and_propose()
    f.create_spec(prop["id"]); f.generate_module_code(prop["id"])
    f.generate_tests(prop["id"]); f.validate_module(prop["id"])
    monkeypatch.setenv("SELF_MODULE_FACTORY_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    r = f.register_shadow(prop["id"])
    assert r["ok"] is False and r["reason"] == "factory disabled"


def test_forbidden_import_still_rejected(tmp_path, monkeypatch):
    # The safety property that must never regress: a module with a forbidden
    # import fails validation even inside the enabled factory.
    from app.brain import repair_queue, self_module_factory as f
    repair_queue.note_failure("tool-failure", tier=1, guardian=True,
                              fix_class="code")
    prop = f.detect_and_propose()
    f.create_spec(prop["id"])
    code_path = f.generate_module_code(prop["id"])
    import pathlib
    p = pathlib.Path(code_path)
    p.write_text("import subprocess\n" + p.read_text())
    f.generate_tests(prop["id"])
    report = f.validate_module(prop["id"])
    assert report["passed"] is False
    assert any("subprocess" in fx for fx in report["failures"])
