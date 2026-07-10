"""Phase 2G — self-awareness + supervised self-improvement (hermetic).

Nothing here touches real git or runs the real coding agent — all mocked.
"""
import types

import pytest


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    from app.config import get_settings
    monkeypatch.setattr("app.brain.self_improve._STATE", tmp_path / "si.json")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Self-repo awareness ─────────────────────────────────────────

def test_self_repo_summary(monkeypatch):
    from app.brain import self_repo

    def fake_git(*args, timeout=20):
        out = {"log": "abc123 fix thing\ndef456 add feature",
               "status": "", "rev-parse": "main"}
        key = "log" if "log" in args else ("status" if "status" in args
                                           else "rev-parse")
        return types.SimpleNamespace(stdout=out[key], returncode=0)

    monkeypatch.setattr(self_repo, "_git", fake_git)
    s = self_repo.summary()
    assert "main" in s and "fix thing" in s


# ── Propose: plan only, no mutation ─────────────────────────────

def test_propose_stores_plan(monkeypatch):
    from app.brain import self_improve
    from app.coding import agent

    fake = agent.AgentRun(task="x", workdir="/x",
                          plan={"understanding": "u", "approach_review": "r",
                                "steps": ["s1"], "risks": [], "files_to_touch": []})
    monkeypatch.setattr(agent, "make_plan", lambda t, w: fake)
    res = self_improve.propose("improve memory recall")
    assert res["ok"] is True and res["id"]
    stored = self_improve.get(res["id"])
    assert stored["status"] == "proposed"
    assert stored["plan"]["steps"] == ["s1"]


def test_propose_disabled(monkeypatch):
    monkeypatch.setenv("SELF_IMPROVE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.brain import self_improve
    assert self_improve.propose("x")["ok"] is False


# ── Apply: requires clean tree, runs on a branch, tests gate ────

def test_apply_refuses_dirty_tree(monkeypatch):
    from app.brain import self_improve
    self_improve._save({"P1": {"id": "P1", "gap": "x", "plan": {},
                               "status": "proposed"}})
    monkeypatch.setattr(self_improve, "recent_changes",
                        lambda: {"branch": "main", "uncommitted": ["a.py"]})
    res = self_improve.apply_async("P1")
    assert res["ok"] is False and "clean" in res["error"]


def test_apply_unknown_proposal(monkeypatch):
    from app.brain import self_improve
    monkeypatch.setattr(self_improve, "recent_changes",
                        lambda: {"branch": "main", "uncommitted": []})
    assert self_improve.apply_async("NOPE")["ok"] is False


def test_run_apply_branch_tests_and_report(monkeypatch):
    """The core safety flow: branch → agent → tests → report, main untouched."""
    from app.brain import self_improve
    from app.coding import agent

    self_improve._save({"P2": {"id": "P2", "gap": "faster recall",
                               "plan": {"steps": ["x"]}, "status": "proposed"}})
    git_calls = []
    monkeypatch.setattr(self_improve, "_git",
                        lambda *a, **k: git_calls.append(a) or
                        types.SimpleNamespace(returncode=0, stdout="main"))
    monkeypatch.setattr(self_improve, "recent_changes",
                        lambda: {"branch": "main", "uncommitted": []})
    monkeypatch.setattr(agent, "execute",
                        lambda *a, **k: agent.AgentRun(
                            task="x", workdir="/x", done=True,
                            changed_files=["app/memory/base_memory.py"]))
    # tests pass
    monkeypatch.setattr(self_improve.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            returncode=0, stdout="390 passed"))
    monkeypatch.setattr(self_improve, "_push_branch",
                        lambda b: "https://github.com/x/compare/main..." + b)
    reports = []
    monkeypatch.setattr(self_improve, "_report",
                        lambda cid, text: reports.append(text))

    self_improve._run_apply("P2", report_conv_id=135)

    prop = self_improve.get("P2")
    assert prop["status"] == "ready_to_review"
    assert prop["tests_passed"] is True
    # created + returned to a branch (checkout appears), never committed to main
    assert any(a[0] == "checkout" and a[1] == "-b" for a in git_calls)
    assert reports and "PASS" in reports[0]
    assert "compare/main" in reports[0]


def test_run_apply_failed_tests_keeps_main_safe(monkeypatch):
    from app.brain import self_improve
    from app.coding import agent

    self_improve._save({"P3": {"id": "P3", "gap": "x", "plan": {},
                               "status": "proposed"}})
    monkeypatch.setattr(self_improve, "_git",
                        lambda *a, **k: types.SimpleNamespace(
                            returncode=0, stdout="main"))
    monkeypatch.setattr(self_improve, "recent_changes",
                        lambda: {"branch": "main", "uncommitted": []})
    monkeypatch.setattr(agent, "execute",
                        lambda *a, **k: agent.AgentRun(task="x", workdir="/x",
                                                       changed_files=["a.py"]))
    monkeypatch.setattr(self_improve.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            returncode=1, stdout="1 failed"))
    monkeypatch.setattr(self_improve, "_push_branch", lambda b: None)
    reports = []
    monkeypatch.setattr(self_improve, "_report",
                        lambda cid, text: reports.append(text))

    self_improve._run_apply("P3", 135)
    assert self_improve.get("P3")["status"] == "failed"
    assert reports and ("nahi hue" in reports[0] or "PASS nahi" in reports[0])


# ── Guardian chat commands ──────────────────────────────────────

def test_repo_command_reports_status(monkeypatch):
    from app.agents import tody_agent
    monkeypatch.setattr("app.brain.self_repo.summary", lambda: "Branch: main\n...")
    reply = tody_agent._guardian_command_reply("what did you change?")
    assert reply and "repo status" in reply.lower()


def test_improve_command_proposes(monkeypatch):
    from app.agents import tody_agent
    monkeypatch.setattr("app.brain.self_improve.propose",
                        lambda gap: {"ok": True, "id": "P9",
                                     "plan": {"steps": ["do X"],
                                              "approach_review": "looks fine"}})
    reply = tody_agent._guardian_command_reply("improve yourself: memory recall")
    assert "P9" in reply and "apply self-improve" in reply.lower()


def test_apply_command_starts(monkeypatch):
    from app.agents import tody_agent
    monkeypatch.setattr("app.brain.self_improve.apply_async",
                        lambda pid, report_conv_id=135: {"ok": True, "started": True})
    reply = tody_agent._guardian_command_reply("apply self-improve P9")
    assert "branch" in reply.lower()


# ── Phase 2H: autonomous gates ──────────────────────────────────

def test_autonomy_gate_blocks_safety_files(monkeypatch):
    from app.brain import self_improve
    from app.coding import agent
    monkeypatch.setattr(self_improve, "_git",
                        lambda *a, **k: __import__("types").SimpleNamespace(
                            returncode=0, stdout="3 insertions(+), 1 deletion"))
    run = agent.AgentRun(task="x", workdir="/x",
                         changed_files=["app/safety/confidential_guard.py"])
    ok, reason = self_improve._autonomy_gate(run, tests_passed=True)
    assert ok is False and "safety" in reason


def test_autonomy_gate_blocks_big_diff(monkeypatch):
    from app.brain import self_improve
    from app.coding import agent
    monkeypatch.setenv("SELF_IMPROVE_MAX_FILES", "2")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(self_improve, "_git",
                        lambda *a, **k: __import__("types").SimpleNamespace(
                            returncode=0, stdout=""))
    run = agent.AgentRun(task="x", workdir="/x",
                         changed_files=["a.py", "b.py", "c.py"])
    ok, reason = self_improve._autonomy_gate(run, tests_passed=True)
    assert ok is False and "files" in reason


def test_autonomy_gate_passes_safe_capability_change(monkeypatch):
    from app.brain import self_improve
    from app.coding import agent
    monkeypatch.setenv("SELF_IMPROVE_PRODUCTION_PROMOTION_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(self_improve, "_git",
                        lambda *a, **k: __import__("types").SimpleNamespace(
                            returncode=0, stdout="10 insertions(+), 2 deletions(-)"))
    monkeypatch.setattr(self_improve, "_daily_count", lambda: 0)
    run = agent.AgentRun(task="x", workdir="/x",
                         changed_files=["app/brain/web_learning.py"])
    ok, reason = self_improve._autonomy_gate(run, tests_passed=True)
    assert ok is True


def test_autonomy_gate_keeps_safe_change_in_research_lane_by_default(monkeypatch):
    from app.brain import self_improve
    from app.coding import agent
    monkeypatch.setenv("SELF_IMPROVE_PRODUCTION_PROMOTION_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(self_improve, "_git",
                        lambda *a, **k: __import__("types").SimpleNamespace(
                            returncode=0, stdout="10 insertions(+), 2 deletions(-)"))
    monkeypatch.setattr(self_improve, "_daily_count", lambda: 0)
    run = agent.AgentRun(task="x", workdir="/x",
                         changed_files=["app/brain/web_learning.py"])

    ok, reason = self_improve._autonomy_gate(run, tests_passed=True)

    assert ok is False
    assert "Parent Kernel" in reason


def test_autonomy_gate_blocks_when_tests_fail():
    from app.brain import self_improve
    from app.coding import agent
    run = agent.AgentRun(task="x", workdir="/x", changed_files=["a.py"])
    ok, reason = self_improve._autonomy_gate(run, tests_passed=False)
    assert ok is False


def test_autonomous_improve_command_self_initiates(monkeypatch):
    monkeypatch.setenv("SELF_IMPROVE_AUTONOMOUS", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.agents import tody_agent
    called = {}
    monkeypatch.setattr("app.brain.self_improve.self_initiate",
                        lambda gap, report_conv_id=135: called.update(gap=gap)
                        or {"ok": True, "id": "X", "started": True})
    reply = tody_agent._guardian_command_reply("improve yourself: faster memory")
    assert "khud" in reply.lower()
    assert "permission nahi" in reply.lower()
    assert called["gap"] == "faster memory"
