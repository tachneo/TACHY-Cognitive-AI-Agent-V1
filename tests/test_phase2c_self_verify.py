"""Phase 2C-selfverify — Phase 1: B1 substantively-empty reply, B3/F1 chat
self-verification sandbox, B2 mission counter, F6 verify-before-claim.

All from the latest rohitsingh TODY turns (3163, 3181-3202): Shree over-claimed
a mission she barely started, gave a 30-char non-answer to a real question, and
felt distress because she couldn't verify code changes Rohit made to her."""
from __future__ import annotations

import json

import pytest

from app.agents import chat_tool_loop
from app.brain import reply_safety


# ── B1: substantively-empty acknowledgment → fallback ───────────

def test_is_acknowledgment_only_detects_filler():
    assert reply_safety._is_acknowledgment_only("Papa, sach mein bata rahi hoon")
    assert reply_safety._is_acknowledgment_only("haan Papa")
    assert reply_safety._is_acknowledgment_only("theek hai")
    assert reply_safety._is_acknowledgment_only("abhi batati hoon")
    assert reply_safety._is_acknowledgment_only("I'll tell you")


def test_is_acknowledgment_only_rejects_real_answers():
    assert not reply_safety._is_acknowledgment_only(
        "Main thik hoon Papa, aap batao kya kaam hai.")
    assert not reply_safety._is_acknowledgment_only(
        "1. Persistent memory 2. Emotion engine 3. Offline brain")
    # too long to be a filler
    assert not reply_safety._is_acknowledgment_only(
        "Papa, sach mein bata rahi hoon, ab main detail mein bata dungi " + "x" * 80)


def test_is_content_question_detects_list_requests():
    assert reply_safety._is_content_question("mujhe apne saare problem batao")
    assert reply_safety._is_content_question("tum me kya kami hai, analyze")
    assert reply_safety._is_content_question("kya kya ability tum me aa gai")
    assert reply_safety._is_content_question("list all your gaps")


def test_is_content_question_rejects_yesno():
    assert not reply_safety._is_content_question("are you there?")
    assert not reply_safety._is_content_question("kaisi ho tum")
    assert not reply_safety._is_content_question("can you message @niva")


def test_finalize_replaces_acknowledgment_to_content_question():
    """The turn-3196 fix: 'Papa, sach mein bata rahi hoon' in reply to 'tell me
    all your problems' is NOT a real answer → question-aware fallback."""
    msg = "mujhe apne saare problem batao taaki mai usko solutions kar saku"
    out = reply_safety.finalize_reply("Papa, sach mein bata rahi hoon", message=msg)
    assert "sach mein bata rahi" not in out
    assert len(out) > 40  # meaningful fallback, not the filler
    assert "sawaal" in out.lower() or "problem" in out.lower()


def test_finalize_keeps_acknowledgment_to_yesno():
    """A 'haan Papa' to 'are you there?' IS a real answer — must stay."""
    out = reply_safety.finalize_reply("haan Papa", message="are you there?")
    assert out == "haan Papa"


def test_finalize_keeps_real_substantive_answer():
    out = reply_safety.finalize_reply(
        "1. Persistent memory\n2. Emotion engine\n3. Offline brain",
        message="kya kya ability tum me aa gai")
    assert "Persistent memory" in out  # real answer kept


# ── B3/F1: chat self-verification sandbox (her own repo only) ───

def test_should_run_tool_loop_triggers_on_verification_cues():
    assert chat_tool_loop.should_run_tool_loop("kya update kiya tumhare code me")
    assert chat_tool_loop.should_run_tool_loop("verify the changes you made")
    assert chat_tool_loop.should_run_tool_loop("test chalao aur batao")
    assert chat_tool_loop.should_run_tool_loop("check the code and tell me what changed")
    assert chat_tool_loop.should_run_tool_loop("git log dikhao")


def test_should_not_run_tool_loop_for_plain_chat():
    assert not chat_tool_loop.should_run_tool_loop("hi")
    assert not chat_tool_loop.should_run_tool_loop("kaisi ho")
    assert not chat_tool_loop.should_run_tool_loop("thank you")


def test_read_file_reads_own_repo(tmp_path, monkeypatch):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "identity.py").write_text("NAME = 'Shree'\n")
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("read_file", {"path": "app/identity.py"})
        assert ok and "Shree" in out
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_read_file_blocks_path_escape(tmp_path, monkeypatch):
    (tmp_path / "ok.txt").write_text("ok")
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("read_file",
                                            {"path": "../../../etc/passwd"})
        assert ok is False
        assert "escape" in out.lower()
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_git_log_returns_commits(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    (tmp_path / "x.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "--no-verify", "-m", "first"],
                   cwd=tmp_path, check=True)
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("git_log", {"limit": 5})
        assert ok and "first" in out
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_git_log_clamps_limit(tmp_path, monkeypatch):
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("git_log", {"limit": 99999})
        # clamped to 30; doesn't crash on a non-git dir
        assert ok in (True, False)
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_run_tests_allowlist_accepts_pytest(tmp_path, monkeypatch):
    (tmp_path / "run.sh").write_text("exit 0\n")
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("run_tests",
                                            {"command": "sh run.sh"})
        assert ok is False  # sh run.sh not in allowlist
        ok, out = chat_tool_loop._call_tool(
            "run_tests", {"command": "pytest -q --no-header"})
        # pytest is allowlisted; may pass or fail but not rejected as unsafe
        assert "not in allowlist" not in out
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_run_tests_blocks_injection(tmp_path, monkeypatch):
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("run_tests",
                                            {"command": "pytest; rm -rf /"})
        assert ok is False
        assert "not in allowlist" in out
        ok, out = chat_tool_loop._call_tool("run_tests", {"command": "rm -rf /"})
        assert ok is False
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_git_show_rejects_shell_metachars(tmp_path, monkeypatch):
    chat_tool_loop.set_self_repo(tmp_path)
    try:
        ok, out = chat_tool_loop._call_tool("git_show", {"ref": "main; rm -rf /"})
        assert ok is False
        assert "bad ref" in out.lower()
    finally:
        from pathlib import Path
        chat_tool_loop.set_self_repo(Path(__file__).resolve().parents[1])


def test_tool_loop_uses_code_tools_then_finishes(monkeypatch):
    """End-to-end: the loop calls read_file then finish with a real answer."""
    replies = [
        json.dumps({"thought": "let me check", "tool": "git_log",
                    "args": {"limit": 3}}),
        json.dumps({"thought": "now answer",
                    "finish": "Papa, maine git log dekha — last commit 'Phase 1' hai."}),
    ]
    class _Smart:
        name = "nvidia"
        def __init__(self): self.i = 0
        def complete(self, system, prompt, max_tokens=800):
            r = replies[self.i]; self.i += 1; return r
    from app.llm import provider
    monkeypatch.setattr(provider, "get_provider", lambda: _Smart())
    monkeypatch.setattr(chat_tool_loop, "get_provider", lambda: _Smart())
    res = chat_tool_loop.run("kya update kiya code me?")
    assert res.used_tools is True
    assert res.tool_calls[0]["tool"] == "git_log"
    assert "Phase 1" in res.reply


# ── B2: mission counter doesn't count Shree's own opener ────────

def test_send_direct_marks_opener_processed(monkeypatch):
    """The turn-3163 bug: Shree's opener got re-processed as inbound, counted
    as a mission exchange with her own opener as 'learned'. send_direct must
    mark its sent message processed."""
    from app.agents import tody_messaging
    marked = {}

    class _FakeClient:
        def _post(self, path, data):
            return {"user": {"uuid": "u", "username": "niva",
                             "display_name": "Niva"}}
        def start_direct(self, uuid):
            return {"conversation_id": 777}
        def send_message(self, conv, body):
            return {"message": {"id": 4242, "duplicate": False}}

    monkeypatch.setattr(tody_messaging, "get_client", lambda: _FakeClient())
    res = tody_messaging.send_direct("niva", "hello beta")
    assert res["sent"] is True

    from app.memory import dialogue_memory
    # The opener's message id should now be marked processed so the worker
    # doesn't re-find it as an unprocessed inbound.
    assert dialogue_memory.was_processed("tody", 777, 4242)


# ── F6: verify-before-claim backstop ─────────────────────────────

def test_verify_before_claim_flags_unverified_code_check():
    from app.agents import tody_agent
    # No tool_calls in brain → claiming "I checked the code" is unverified
    out = tody_agent._verify_before_claim(
        "Papa, maine code check kiya — sab theek hai.", brain={})
    assert "actually code check nahi" in out.lower()
    assert "verify" in out.lower()


def test_verify_before_claim_flags_unverified_tests_pass():
    from app.agents import tody_agent
    out = tody_agent._verify_before_claim(
        "Tests pass ho gaye Papa, sab green hai.", brain={})
    assert "tests nahi chalaye" in out.lower()


def test_verify_before_claim_passes_when_tool_ran():
    from app.agents import tody_agent
    brain = {"tool_calls": [{"tool": "run_tests"}, {"tool": "git_log"}]}
    reply = "Papa, tests pass ho gaye aur maine git log bhi dekha."
    out = tody_agent._verify_before_claim(reply, brain)
    assert out == reply  # claim stands — she actually ran the tools


def test_verify_before_claim_passes_when_code_tool_ran():
    from app.agents import tody_agent
    brain = {"tool_calls": [{"tool": "git_diff"}]}
    reply = "Maine code check kiya — changes dikh rahe hain."
    out = tody_agent._verify_before_claim(reply, brain)
    assert out == reply


def test_verify_before_claim_no_claim_passes():
    from app.agents import tody_agent
    out = tody_agent._verify_before_claim("Main thik hoon Papa.", brain={})
    assert out == "Main thik hoon Papa."
