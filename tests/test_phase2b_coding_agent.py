"""Phase 2B — Shree coding agent: sandboxed tools + plan-first loop (hermetic)."""
import json

import pytest

from app.coding import agent
from app.coding import tools as T


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "README.md").write_text("# demo\n")
    return tmp_path


# ── Sandbox / tools ─────────────────────────────────────────────

def test_sandbox_blocks_escape(repo):
    sb = T.Sandbox(repo)
    with pytest.raises(PermissionError):
        sb.resolve("../etc/passwd")
    assert sb.read_file("../../etc/passwd").ok is False


def test_read_list_glob_grep(repo):
    sb = T.Sandbox(repo)
    assert "def add" in sb.read_file("app/main.py").output
    assert "app/" in sb.list_dir(".").output
    assert "app/main.py" in sb.glob("*.py").output
    hit = sb.grep("return", "app/main.py")
    assert "main.py:2" in hit.output


def test_write_and_edit(repo):
    sb = T.Sandbox(repo)
    assert sb.write_file("app/new.py", "x = 1\n").ok
    assert (repo / "app" / "new.py").read_text() == "x = 1\n"
    res = sb.edit_file("app/main.py", "a - b", "a + b")
    assert res.ok and (repo / "app" / "main.py").read_text().endswith("a + b\n")


def test_edit_requires_unique_match(repo):
    sb = T.Sandbox(repo)
    (repo / "dup.py").write_text("x\nx\n")
    assert sb.edit_file("dup.py", "x", "y").ok is False  # not unique
    assert sb.edit_file("app/main.py", "NOPE", "y").ok is False  # not found


def test_bash_runs_in_sandbox(repo):
    sb = T.Sandbox(repo)
    assert "README.md" in sb.run_bash("ls").output


def test_destructive_detection():
    assert T.is_destructive("rm -rf /")
    assert T.is_destructive("git push origin main")
    assert not T.is_destructive("ls -la")
    assert not T.is_destructive("pytest -q")


# ── JSON extraction ─────────────────────────────────────────────

def test_extract_json_tolerates_fences_and_prose():
    assert agent._extract_json('```json\n{"a":1}\n```')["a"] == 1
    assert agent._extract_json('sure!\n{"tool":"read_file"} done')["tool"] \
        == "read_file"
    assert agent._extract_json("no json here") is None


# ── Plan-first (read-only, no mutation) ─────────────────────────

class _ScriptedLLM:
    """Feeds a fixed sequence of JSON replies, ignoring the prompt."""

    name = "fake"

    def __init__(self, replies):
        self._replies = list(replies)

    def complete(self, system, prompt, max_tokens=800):
        return self._replies.pop(0) if self._replies else '{"done":true,"summary":"ok"}'


def test_make_plan_uses_readonly_then_returns_plan(repo, monkeypatch):
    llm = _ScriptedLLM([
        '{"thought":"look","tool":"read_file","args":{"path":"app/main.py"}}',
        json.dumps({"plan": {"understanding": "fix add()",
                             "approach_review": "your subtraction is a bug; use +",
                             "steps": ["edit main.py"], "risks": [],
                             "files_to_touch": ["app/main.py"]}}),
    ])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    run = agent.make_plan("fix add() to actually add", str(repo))
    assert run.plan and "bug" in run.plan["approach_review"]
    assert run.turns[0].tool == "read_file"       # it read before planning
    # planning must not mutate the repo
    assert (repo / "app" / "main.py").read_text() == "def add(a, b):\n    return a - b\n"


def test_plan_phase_refuses_mutating_tools(repo, monkeypatch):
    llm = _ScriptedLLM([
        '{"thought":"try to write","tool":"write_file","args":{"path":"x","content":"y"}}',
        json.dumps({"plan": {"understanding": "x", "approach_review": "y",
                             "steps": [], "risks": [], "files_to_touch": []}}),
    ])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    run = agent.make_plan("do something", str(repo))
    assert run.turns[0].ok is False              # write blocked during planning
    assert not (repo / "x").exists()


# ── Execute (full loop, real edit) ──────────────────────────────

def test_execute_edits_file_and_finishes(repo, monkeypatch):
    llm = _ScriptedLLM([
        '{"thought":"read","tool":"read_file","args":{"path":"app/main.py"}}',
        '{"thought":"fix the bug","tool":"edit_file","args":{"path":"app/main.py",'
        '"old":"a - b","new":"a + b"}}',
        '{"thought":"done","done":true,"summary":"Fixed add() to use +."}',
        '{"approved":true,"note":"correct"}',   # self-review pass
    ])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    run = agent.execute("fix add()", str(repo), autonomy="yolo", verify=False)
    assert run.done is True
    assert "app/main.py" in run.changed_files
    assert (repo / "app" / "main.py").read_text().endswith("a + b\n")
    assert run.steps >= 3 and run.tokens_est > 0


def test_execute_gates_bash_in_plan_first(repo, monkeypatch):
    llm = _ScriptedLLM([
        '{"thought":"run","tool":"run_bash","args":{"command":"echo hi"}}',
        '{"thought":"done","done":true,"summary":"n/a"}',
    ])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    denied = agent.execute("x", str(repo), autonomy="plan_first",
                           approver=lambda w: False)
    assert denied.turns[0].ok is False           # bash needed approval, denied


def test_coding_provider_falls_back_without_anthropic_key(monkeypatch):
    monkeypatch.setenv("CODING_ANTHROPIC_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.llm.provider import get_coding_provider
    # No key → falls back to the default provider (heuristic in tests).
    assert get_coding_provider().name in {"heuristic", "nvidia", "huggingface"}
    get_settings.cache_clear()


def test_verify_gate_rejects_bare_done_until_tests_pass(repo, monkeypatch):
    # 'done' but tests fail → agent must keep working; then a passing edit.
    (repo / "run_tests.sh").write_text("exit 1\n")
    monkeypatch.setenv("CODING_TEST_COMMAND", "sh run_tests.sh")
    from app.config import get_settings
    get_settings.cache_clear()
    llm = _ScriptedLLM([
        '{"thought":"claim done early","done":true,"summary":"premature"}',
        # after verification failure feedback, fix the test then finish
        '{"thought":"make tests pass","tool":"write_file","args":'
        '{"path":"run_tests.sh","content":"exit 0\\n"}}',
        '{"thought":"now done","done":true,"summary":"fixed"}',
        '{"approved":true,"note":"ok"}',
    ])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    run = agent.execute("make the suite pass", str(repo), autonomy="yolo")
    assert run.verified is True and run.done is True
    get_settings.cache_clear()


def test_self_review_forces_fix_before_done(repo, monkeypatch):
    llm = _ScriptedLLM([
        '{"thought":"done","done":true,"summary":"first attempt"}',
        '{"approved":false,"issues":["forgot to handle n=0"]}',   # review rejects
        '{"thought":"handle it","tool":"write_file","args":'
        '{"path":"app/main.py","content":"def add(a,b):\\n    return a+b\\n"}}',
        '{"thought":"done for real","done":true,"summary":"handled edge case"}',
        '{"approved":true,"note":"good now"}',
    ])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    run = agent.execute("fix add()", str(repo), autonomy="yolo", verify=False)
    assert run.done is True
    assert "handled edge case" in run.summary


def test_stuck_detection_stops_thrashing(repo, monkeypatch):
    # Same failing edit over and over → agent stops instead of looping to limit.
    bad = ('{"thought":"try","tool":"edit_file","args":{"path":"app/main.py",'
           '"old":"DOES_NOT_EXIST","new":"x"}}')
    llm = _ScriptedLLM([bad, bad, bad, bad, bad])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    run = agent.execute("do impossible", str(repo), autonomy="yolo", verify=False)
    assert run.stuck is True
    assert run.steps < 6          # stopped early, did not burn all steps


def test_repo_profile_detects_python_and_tests(repo):
    from app.coding import repo_profile
    (repo / "pyproject.toml").write_text("[tool.pytest]\n")
    prof = repo_profile.build(str(repo))
    assert "Python" in prof["languages"]
    assert "pytest" in (prof["test_command"] or "")
    assert "REPOSITORY PROFILE" in repo_profile.as_prompt(prof)


def test_transcript_compaction_bounds_length():
    long = [{"role": "user", "content": "task"}]
    for i in range(60):
        long.append({"role": "assistant", "content": f'{{"tool":"read_file{i}"}}'})
        long.append({"role": "user", "content": f"result {i}"})
    out = agent._compact(long, keep_recent=16)
    assert len(out) <= 18
    assert out[0]["content"] == "task"          # task preserved
    assert "elided" in out[1]["content"]


def test_cli_plan_only_smoke(repo, monkeypatch, capsys):
    llm = _ScriptedLLM([json.dumps({"plan": {"understanding": "u",
                        "approach_review": "r", "steps": ["s"], "risks": [],
                        "files_to_touch": []}})])
    monkeypatch.setattr(agent, "get_coding_provider", lambda: llm)
    from app.coding import cli
    rc = cli.main(["--plan", "-C", str(repo), "do a thing"])
    assert rc == 0
    assert "Shree's plan" in capsys.readouterr().out
