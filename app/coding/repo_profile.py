"""Repo profile (Phase 2C) — grounds Shree in the codebase before she acts.

Detects the languages, the test command, entry points, and any conventions
docs, so every plan/execute prompt is anchored in THIS repo instead of generic
guesses. Cheap, cached per working directory + tree state.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

_EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".php": "PHP", ".go": "Go", ".rb": "Ruby",
    ".java": "Java", ".kt": "Kotlin", ".rs": "Rust", ".c": "C", ".cpp": "C++",
    ".cs": "C#", ".sql": "SQL", ".sh": "Shell",
}
_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
         "build", ".next", "vendor", "storage"}
_CONVENTION_FILES = ("AGENTS.md", "CLAUDE.md", "CONVENTIONS.md",
                     "CONTRIBUTING.md", ".shree.md")


def _detect_test_command(root: Path) -> str | None:
    if (root / "pytest.ini").exists() or (root / "tests").is_dir() \
            or _pyproject_has(root, "pytest"):
        return ".venv/bin/pytest -q -p no:cacheprovider" \
            if (root / ".venv").exists() else "pytest -q"
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
            if "test" in scripts:
                return "npm test --silent"
        except (ValueError, OSError):
            pass
    if (root / "phpunit.xml").exists() or (root / "phpunit.xml.dist").exists():
        return "./vendor/bin/phpunit"
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test"
    return None


def _pyproject_has(root: Path, needle: str) -> bool:
    p = root / "pyproject.toml"
    try:
        return needle in p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _tree_signature(root: Path) -> str:
    """Cheap change key: newest mtime among a few marker files + dir count."""
    markers = ("pyproject.toml", "package.json", "go.mod", "composer.json",
               "requirements.txt")
    latest = 0.0
    for m in markers:
        p = root / m
        if p.exists():
            latest = max(latest, p.stat().st_mtime)
    return f"{latest:.0f}"


_CACHE: dict[str, tuple[str, dict]] = {}


def build(workdir: str, *, max_files: int = 4000) -> dict:
    root = Path(workdir).resolve()
    sig = _tree_signature(root)
    cached = _CACHE.get(str(root))
    if cached and cached[0] == sig:
        return cached[1]

    langs: Counter[str] = Counter()
    top_dirs: list[str] = []
    seen = 0
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        if entry.is_dir() and entry.name not in _SKIP \
                and not entry.name.startswith("."):
            top_dirs.append(entry.name + "/")
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in _SKIP and not d.startswith(".")]
        for name in fn:
            lang = _EXT_LANG.get(Path(name).suffix)
            if lang:
                langs[lang] += 1
            seen += 1
            if seen > max_files:
                break
        if seen > max_files:
            break

    conventions = ""
    for cf in _CONVENTION_FILES:
        p = root / cf
        if p.exists():
            try:
                conventions = f"{cf}:\n{p.read_text(encoding='utf-8')[:1500]}"
                break
            except (OSError, UnicodeDecodeError):
                pass
    readme = ""
    for rf in ("README.md", "README.rst", "README.txt"):
        p = root / rf
        if p.exists():
            try:
                readme = p.read_text(encoding="utf-8")[:600]
                break
            except (OSError, UnicodeDecodeError):
                pass

    profile = {
        "languages": [lang for lang, _ in langs.most_common(4)],
        "top_dirs": top_dirs[:12],
        "test_command": _detect_test_command(root),
        "conventions": conventions,
        "readme": readme,
    }
    _CACHE[str(root)] = (sig, profile)
    return profile


def as_prompt(profile: dict) -> str:
    parts = []
    if profile.get("languages"):
        parts.append("Languages: " + ", ".join(profile["languages"]))
    if profile.get("top_dirs"):
        parts.append("Top-level: " + " ".join(profile["top_dirs"]))
    if profile.get("test_command"):
        parts.append(f"Test command: `{profile['test_command']}`")
    if profile.get("readme"):
        parts.append("README (excerpt):\n" + profile["readme"])
    if profile.get("conventions"):
        parts.append("Project conventions:\n" + profile["conventions"])
    return "REPOSITORY PROFILE\n" + "\n".join(parts) if parts else ""
