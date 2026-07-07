"""Risk classifier — score a Shree *tool call* (tool name + args) or a shell
command into the brain's ``RiskTier``.

``app.safety.policy.classify`` maps an *action name* (e.g. ``production_deploy``)
to a tier. That is too coarse for a coding agent, where the risk lives in the
arguments: ``run_bash("ls")`` is low risk, ``run_bash("rm -rf /")`` is forbidden,
and ``edit_file`` on ``.env`` is high risk. This module adds the argument-aware
view used by Shree's tool dispatch, while reusing the same ``RiskTier`` enum so
the rest of the brain (approval gate, audit log) speaks one language.
"""
from __future__ import annotations

import re

from app.safety.policy import RiskTier

_READ_TOOLS = {"read_file", "list_dir", "glob", "grep"}

# Paths that imply secrets/credentials -> any access is HIGH (access_secrets).
_SECRETS_PATH = re.compile(
    r"(^|/)(?:\.env(?:\.[A-Za-z0-9_]+)?|\.envrc|credentials|creds|secrets|"
    r"\.netrc|\.npmrc|\.pypirc|\.aws/|\.ssh/|id_rsa|id_ed25519|id_ecdsa|"
    r".*\.pem|.*\.key|.*\.keystore|.*\.p12|.*\.pfx)(?:$|/)", re.I)

# System/critical paths -> HIGH (could brick the box or the repo).
_CRITICAL_PATH = re.compile(r"^/(?:etc|root|var|usr|bin|sbin|boot|proc|sys)\b")

# Commands that are FORBIDDEN outright — no approver can authorize them.
_FORBIDDEN_CMD = re.compile(
    r"(?:\bmkfs[\s.]|\bdd\s+if=.*\s+of=/dev/|:\s*\(\)\s*\{[^}]*\};|"
    r"\bshutdown(?:\s|$)|\breboot(?:\s|$)|\bhalt(?:\s|$)|\bpoweroff(?:\s|$)|"
    r">\s*/dev/sd[a-z]|\bchmod\s+-R\s+000\b|"
    r"\brm\s+-rf\s+/(?:\s|$)|\brm\s+-rf\s+(?:~|\$HOME)(?:/|\s|$))", re.I)

# Commands that are HIGH risk even with approval — destructive or exfiltrating.
_HIGH_CMD = re.compile(
    r"\b(?:rm\s+-rf?|git\s+push|git\s+reset\s+--hard|git\s+clean\s+-[a-z]*d|"
    r"drop\s+(?:database|table)|truncate\s+table?|alter\s+table.*drop|"
    r"curl[^|]*\|\s*(?:ba)?sh|wget[^|]*\|\s*(?:ba)?sh|"
    r"nc\s+-|netcat|python\s+-c\s+['\"].*socket|"
    r"chmod\s+-R\s+0?77[0-9]\s+/|mv\s+\S+\s+/dev/|"
    r"killall(?:\s|$)|kill(?:\s+-9)?\s+-1)\b", re.I)

# Network egress — flagged HIGH when it can move data out.
_NETWORK_EGRESS = re.compile(
    r"\b(?:curl|wget|nc|netcat|ssh|scp|rsync|ftp|sftp)\b", re.I)

# DB-modifying statements outside a safe migration check.
_DB_MODIFY = re.compile(
    r"\b(?:drop\s+(?:database|table|schema)|truncate|alter\s+table|"
    r"delete\s+from|update\s+\w+\s+set|insert\s+into)\b", re.I)


def classify_tool(tool: str, args: dict | None = None) -> RiskTier:
    """Map a Shree tool call to a risk tier based on its arguments."""
    args = args or {}
    if tool in _READ_TOOLS:
        path = args.get("path", "") or args.get("pattern", "") or "."
        if _CRITICAL_PATH.search(path):
            return RiskTier.HIGH        # reading /etc, /root, ... is high-risk
        if _is_secret_path(path):
            return RiskTier.MEDIUM      # values are redacted before reaching LLM
        return RiskTier.LOW
    if tool in {"write_file", "edit_file"}:
        path = args.get("path", "")
        if _is_critical_or_secret_path(path):
            return RiskTier.HIGH        # editing .env / credentials / keys
        return RiskTier.MEDIUM
    if tool in {"run_bash", "run_tests"}:
        return classify_command(args.get("command", ""))
    return RiskTier.MEDIUM


def classify_command(command: str) -> RiskTier:
    """Map a shell command string to a risk tier."""
    cmd = command or ""
    if _FORBIDDEN_CMD.search(cmd):
        return RiskTier.FORBIDDEN
    if _HIGH_CMD.search(cmd):
        return RiskTier.HIGH
    if _DB_MODIFY.search(cmd):
        return RiskTier.HIGH
    if _NETWORK_EGRESS.search(cmd):
        # Any outbound network tooling is at least HIGH without a clear local
        # target; the approver can still allow it in plan_first/auto.
        return RiskTier.HIGH
    return RiskTier.LOW


def _is_critical_or_secret_path(path: str) -> bool:
    if not path or path == ".":
        return False
    if _CRITICAL_PATH.search(path):
        return True
    return _is_secret_path(path)


def _is_secret_path(path: str) -> bool:
    if not path or path == ".":
        return False
    return bool(_SECRETS_PATH.search(path))


def reason(tool: str, tier: RiskTier) -> str:
    """Human-readable reason for a tier, shown to Rohit in alerts."""
    if tier is RiskTier.FORBIDDEN:
        return f"{tool}: forbidden command (destructive/exfiltrating) — blocked."
    if tier is RiskTier.HIGH:
        return (f"{tool}: high-risk (secrets/critical path/destructive/"
                "network) — needs Rohit's approval.")
    if tier is RiskTier.MEDIUM:
        return f"{tool}: medium-risk (code/config change) — proceeding with warning."
    return f"{tool}: low-risk — allowed."
