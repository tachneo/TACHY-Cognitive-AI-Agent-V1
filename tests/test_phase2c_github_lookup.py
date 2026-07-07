"""Phase 2C-selfverify (Phase 2): GitHub self-lookup — Shree reads her OWN repo
when Rohit links it on TODY. Allowlist-enforced; she cannot read other repos."""
from __future__ import annotations

import json

import pytest

from app.agents import chat_tool_loop
from app.tools import github_lookup


@pytest.fixture(autouse=True)
def _github_config(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-test-token")
    monkeypatch.setenv("GITHUB_ALLOWED_REPOS",
                       "tachneo/TACHY-Cognitive-AI-Agent-V1")
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── allowlist enforcement ────────────────────────────────────────

def test_allowed_repos_parsed():
    assert github_lookup._allowed_repos() == {"tachneo/tachy-cognitive-ai-agent-v1"}


def test_is_allowed_own_repo():
    assert github_lookup._is_allowed("tachneo", "TACHY-Cognitive-AI-Agent-V1")
    assert github_lookup._is_allowed("TACHNEO", "tachy-cognitive-ai-agent-v1")


def test_is_allowed_blocks_other_repos():
    assert not github_lookup._is_allowed("otheruser", "secrets")
    assert not github_lookup._is_allowed("tachneo", "other-project")


# ── URL parsing ──────────────────────────────────────────────────

def test_parse_github_url_root():
    p = github_lookup.parse_github_url(
        "check https://github.com/tachneo/TACHY-Cognitive-AI-Agent-V1")
    assert p == {"owner": "tachneo",
                 "repo": "TACHY-Cognitive-AI-Agent-V1", "path": ""}


def test_parse_github_url_with_path():
    p = github_lookup.parse_github_url(
        "https://github.com/tachneo/TACHY-Cognitive-AI-Agent-V1/tree/main/app/brain/cognitive_loop.py")
    assert p["owner"] == "tachneo"
    assert p["repo"] == "TACHY-Cognitive-AI-Agent-V1"
    assert "app/brain" in p["path"]


def test_parse_github_url_no_url():
    assert github_lookup.parse_github_url("kaisi ho tum") is None


def test_mentions_github():
    assert github_lookup.mentions_github("check github.com/tachneo/x")
    assert not github_lookup.mentions_github("kaisi ho")


# ── read_path blocks non-allowlisted repos even with token ───────

def test_read_path_blocks_other_repo(monkeypatch):
    ok, out = github_lookup.read_path("otheruser", "secrets", "")
    assert ok is False
    assert "only read my own repo" in out


def test_read_path_no_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "")
    from app.config import get_settings
    get_settings.cache_clear()
    ok, out = github_lookup.read_path(
        "tachneo", "TACHY-Cognitive-AI-Agent-V1", "")
    assert ok is False
    assert "not configured" in out.lower()


# ── tool-loop integration ────────────────────────────────────────

def test_should_run_tool_loop_triggers_on_github_link():
    assert chat_tool_loop.should_run_tool_loop(
        "check https://github.com/tachneo/TACHY-Cognitive-AI-Agent-V1")
    assert chat_tool_loop.should_run_tool_loop(
        "github pe kya update kiya tumne")


def test_github_read_tool_blocks_other_repo():
    ok, out = chat_tool_loop._call_tool(
        "github_read", {"owner": "otheruser", "repo": "secrets", "path": ""})
    assert ok is False
    assert "only read my own repo" in out


def test_github_read_tool_accepts_url_arg():
    """A github.com URL as the arg is parsed for owner/repo/path."""
    # No token in this branch → returns the not-configured message, but must
    # NOT return the 'missing owner/repo' error (proves URL was parsed).
    ok, out = chat_tool_loop._call_tool(
        "github_read",
        {"url": "https://github.com/tachneo/TACHY-Cognitive-AI-Agent-V1/blob/main/README.md"})
    # owner/repo were parsed (allowlisted) → the only failure is token-related
    assert "missing owner/repo" not in out


def test_github_commits_tool_blocks_other_repo():
    ok, out = chat_tool_loop._call_tool(
        "github_commits", {"owner": "someone", "repo": "else"})
    assert ok is False
    assert "only read my own repo" in out


def test_github_read_missing_args():
    ok, out = chat_tool_loop._call_tool("github_read", {})
    assert ok is False
    assert "missing" in out.lower()
