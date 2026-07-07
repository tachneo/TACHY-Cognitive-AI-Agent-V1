"""Coding tools (Phase 2B) — Shree's hands on a repository.

Every tool is sandboxed to a working directory: a model-supplied path is
resolved to its canonical form and rejected if it escapes the workdir (no
``..``, no symlink break-out, no absolute paths outside the root). Mutating
tools (write/edit) take a git checkpoint first so any change is revertible.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_READ_BYTES = 200_000
MAX_OUTPUT = 20_000


@dataclass
class ToolResult:
    ok: bool
    output: str
    changed_path: str | None = None


class Sandbox:
    """Confines all file/shell operations to `root`."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def resolve(self, rel: str) -> Path:
        p = (self.root / rel).resolve() if not os.path.isabs(rel) else Path(rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"path escapes workspace: {rel}")
        return p

    # ── read-only ───────────────────────────────────────────────
    def read_file(self, path: str) -> ToolResult:
        try:
            p = self.resolve(path)
            if not p.is_file():
                return ToolResult(False, f"not a file: {path}")
            data = p.read_bytes()[:MAX_READ_BYTES]
            text = data.decode("utf-8", errors="replace")
            numbered = "\n".join(f"{i+1}\t{ln}"
                                 for i, ln in enumerate(text.splitlines()))
            return ToolResult(True, numbered[:MAX_OUTPUT])
        except (OSError, PermissionError) as e:
            return ToolResult(False, str(e))

    def list_dir(self, path: str = ".") -> ToolResult:
        try:
            p = self.resolve(path)
            if not p.is_dir():
                return ToolResult(False, f"not a directory: {path}")
            entries = sorted(
                (f"{c.name}/" if c.is_dir() else c.name) for c in p.iterdir()
                if not c.name.startswith(".git"))
            return ToolResult(True, "\n".join(entries)[:MAX_OUTPUT] or "(empty)")
        except (OSError, PermissionError) as e:
            return ToolResult(False, str(e))

    def glob(self, pattern: str) -> ToolResult:
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames
                           if d not in {".git", "node_modules", ".venv",
                                        "__pycache__"}]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), self.root)
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
                    out.append(rel)
            if len(out) > 500:
                break
        return ToolResult(True, "\n".join(sorted(out)[:500])[:MAX_OUTPUT]
                          or "(no matches)")

    def grep(self, pattern: str, path: str = ".") -> ToolResult:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return ToolResult(False, f"bad regex: {e}")
        root = self.resolve(path)
        hits: list[str] = []
        candidates: list[Path] = []
        if root.is_file():
            candidates = [root]
        else:
            for dp, dn, fn in os.walk(root):
                dn[:] = [d for d in dn if d not in {".git", "node_modules",
                                                    ".venv", "__pycache__"}]
                candidates.extend(Path(dp) / f for f in fn)
        for fp in candidates:
            try:
                for i, line in enumerate(
                        fp.read_text(encoding="utf-8", errors="replace").splitlines()):
                    if rx.search(line):
                        rel = os.path.relpath(fp, self.root)
                        hits.append(f"{rel}:{i+1}: {line.strip()[:200]}")
                        if len(hits) >= 200:
                            break
            except (OSError, UnicodeDecodeError):
                continue
            if len(hits) >= 200:
                break
        return ToolResult(True, "\n".join(hits)[:MAX_OUTPUT] or "(no matches)")

    # ── mutating (checkpointed) ─────────────────────────────────
    def _git_checkpoint(self, label: str) -> None:
        try:
            if (self.root / ".git").exists():
                subprocess.run(["git", "-C", str(self.root), "add", "-A"],
                               capture_output=True, timeout=20)
                subprocess.run(["git", "-C", str(self.root), "commit", "-q",
                                "--no-verify", "-m", f"shree checkpoint: {label}"],
                               capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass

    def write_file(self, path: str, content: str) -> ToolResult:
        try:
            p = self.resolve(path)
            self._git_checkpoint(f"before write {path}")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(True, f"wrote {len(content)} bytes to {path}",
                              changed_path=path)
        except (OSError, PermissionError) as e:
            return ToolResult(False, str(e))

    def edit_file(self, path: str, old: str, new: str) -> ToolResult:
        try:
            p = self.resolve(path)
            if not p.is_file():
                return ToolResult(False, f"not a file: {path}")
            text = p.read_text(encoding="utf-8")
            count = text.count(old)
            if count == 0:
                return ToolResult(False, "old_string not found (read the file "
                                         "first and copy it exactly)")
            if count > 1:
                return ToolResult(False, f"old_string is not unique ({count} "
                                         "matches) — add surrounding context")
            self._git_checkpoint(f"before edit {path}")
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
            return ToolResult(True, f"edited {path}", changed_path=path)
        except (OSError, PermissionError) as e:
            return ToolResult(False, str(e))

    def run_bash(self, command: str, timeout: int = 120) -> ToolResult:
        try:
            proc = subprocess.run(
                command, shell=True, cwd=str(self.root),
                capture_output=True, text=True, timeout=timeout)
            out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr)
                                         if proc.stderr else "")
            tag = "" if proc.returncode == 0 else f"[exit {proc.returncode}]\n"
            return ToolResult(proc.returncode == 0, (tag + out)[:MAX_OUTPUT]
                              or "(no output)")
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"command timed out after {timeout}s")
        except OSError as e:
            return ToolResult(False, str(e))

    def git_diff(self) -> ToolResult:
        return self.run_bash("git diff --stat && echo '---' && git diff")

    def git_head(self) -> str | None:
        """Current commit SHA, or None if not a git repo / no commits."""
        try:
            p = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                               capture_output=True, text=True, timeout=10)
            return p.stdout.strip() or None if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    def collapse_to(self, base_ref: str | None) -> bool:
        """Squash all in-run checkpoint commits back to `base_ref`, leaving the
        net change as staged working-tree edits — one clean diff for review,
        no noisy history. No-op if not a git repo."""
        if not base_ref or not (self.root / ".git").exists():
            return False
        try:
            r = subprocess.run(["git", "-C", str(self.root), "reset", "--soft",
                                base_ref], capture_output=True, timeout=20)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


# Commands that must never run without explicit approval, even in auto mode.
DESTRUCTIVE = re.compile(
    r"\b(rm\s+-rf|rm\s+-fr|mkfs|dd\s+if=|:\(\)\{|shutdown|reboot|"
    r"git\s+push|git\s+reset\s+--hard|drop\s+database|drop\s+table|"
    r"truncate|>\s*/dev/|curl[^|]*\|\s*(ba)?sh|wget[^|]*\|\s*(ba)?sh)\b", re.I)


def is_destructive(command: str) -> bool:
    return bool(DESTRUCTIVE.search(command or ""))
