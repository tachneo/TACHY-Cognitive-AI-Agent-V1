"""Self-repo awareness (Phase 2G) — Shree can read her own codebase.

She lives at SHREE_HOME (this repo). This lets her answer "what did you change?"
/ "check the repo" honestly, and grounds self-improvement in her real code
instead of guessing. Read-only.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

SHREE_HOME = Path(__file__).resolve().parents[2]  # /var/www/maa.tachy.in


def _git(*args: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(SHREE_HOME), *args],
                          capture_output=True, text=True, timeout=timeout)


def recent_changes(n: int = 8) -> dict:
    """Recent commits + any uncommitted changes in her own repo."""
    try:
        log = _git("log", "--oneline", "-n", str(n))
        status = _git("status", "--short")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        return {
            "branch": branch.stdout.strip(),
            "recent_commits": [l for l in log.stdout.strip().splitlines() if l],
            "uncommitted": [l for l in status.stdout.strip().splitlines() if l],
        }
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": str(e), "recent_commits": [], "uncommitted": []}


def module_stats() -> dict:
    """Coarse map of her own code: module + test counts."""
    py = list((SHREE_HOME / "app").rglob("*.py")) if (SHREE_HOME / "app").is_dir() else []
    tests = list((SHREE_HOME / "tests").rglob("test_*.py")) \
        if (SHREE_HOME / "tests").is_dir() else []
    return {"modules": len(py), "test_files": len(tests)}


def summary() -> str:
    """A short human-readable 'here's what changed in me recently'."""
    rc = recent_changes(6)
    if rc.get("error"):
        return f"Apne repo ko abhi read nahi kar payi: {rc['error']}"
    lines = [f"Branch: {rc['branch']}", "Recent changes (commits):"]
    lines += [f"  • {c}" for c in rc["recent_commits"]] or ["  (none)"]
    if rc["uncommitted"]:
        lines.append(f"Uncommitted files: {len(rc['uncommitted'])}")
    st = module_stats()
    lines.append(f"Codebase: {st['modules']} modules, {st['test_files']} test files.")
    return "\n".join(lines)
