"""GitHub self-lookup — let Shree read her OWN repo from chat when Rohit links it.

Problem from the rohitsingh chat log (turn 3091): Rohit pasted a GitHub link and
Shree said "GitHub link dekhne ka direct access mere paas abhi nahi hai." She
couldn't verify what was on GitHub vs what's deployed locally.

This tool gives her read-only access to ONE allowlisted repo — her own
(tachneo/TACHY-Cognitive-AI-Agent-V1) — so she can read a file or list a
directory when Rohit links it. She CANNOT read any other repo: the allowlist is
enforced in code, so even if a message says "read github.com/otheruser/secrets",
the tool refuses.

Endpoints used (all read-only):
  - GET /repos/{owner}/{repo}/contents/{path}  → file content or dir listing
  - GET /repos/{owner}/{repo}/commits          → recent commit list

No mutating endpoints. No git push/pull/PR. Output is secured (secrets redacted,
injection quarantined) before it reaches the LLM.
"""
from __future__ import annotations

import base64
import re

import httpx

from app.config import get_settings
from app.safety.audit_logger import log_event_safe
from app.safety.prompt_injection_guard import inspect as inj_inspect
from app.safety.secret_detector import redact as redact_secrets

_API = "https://api.github.com"
# owner/repo — must match the allowlist exactly (case-insensitive).
_REPO_RE = re.compile(r"^([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)$")
# A github.com URL: github.com/owner/repo[/tree/branch][/path]. The branch is
# matched as a single segment (main/master/dev) so it doesn't swallow the path.
_URL_RE = re.compile(
    r"github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)"
    r"(?:/(?:tree|blob)/[A-Za-z0-9_\-]+(?=/|$))?(/[^?\s]*)?", re.I)


def _allowed_repos() -> set[str]:
    raw = (get_settings().github_allowed_repos or "").strip()
    return {r.strip().lower() for r in raw.split(",") if r.strip()}


def _is_allowed(owner: str, repo: str) -> bool:
    return f"{owner.lower()}/{repo.lower()}" in _allowed_repos()


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    token = (get_settings().github_token or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _secure(text: str, *, source: str) -> str:
    safe, _ = redact_secrets(text or "")
    g = inj_inspect(safe, source=source)
    return g.sanitized if g.blocked else safe


def parse_github_url(text: str) -> dict | None:
    """Extract {owner, repo, path} from a github.com URL in the text, or None."""
    m = _URL_RE.search(text or "")
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    path = (m.group(3) or "").lstrip("/")
    return {"owner": owner, "repo": repo, "path": path}


def read_path(owner: str, repo: str, path: str = "") -> tuple[bool, str]:
    """Read a file or list a directory in the allowlisted repo. Returns
    (ok, secured_output). Refuses repos outside the allowlist."""
    if not _is_allowed(owner, repo):
        log_event_safe("github_lookup_blocked",
                       detail=f"repo={owner}/{repo} not in allowlist",
                       risk_tier="medium", actor="shree")
        return False, (f"I can only read my own repo "
                       f"({get_settings().github_allowed_repos}), not "
                       f"{owner}/{repo}.")
    if not (get_settings().github_token or "").strip():
        return False, "GitHub token not configured — Papa needs to add GITHUB_TOKEN to my .env."
    url = f"{_API}/repos/{owner}/{repo}/contents/{path or ''}"
    try:
        resp = httpx.get(url, headers=_headers(), timeout=30)
    except httpx.HTTPError as exc:
        return False, f"github request failed: {exc}"
    if resp.status_code == 404:
        return False, f"path not found: {path or '(repo root)'}"
    if resp.status_code == 403:
        return False, "GitHub rate-limited or token lacks read scope."
    if resp.status_code != 200:
        return False, f"github returned {resp.status_code}"
    data = resp.json()
    # Directory listing → array of entries
    if isinstance(data, list):
        lines = [f"{e.get('type', '?'):4} {e.get('name', '?')}"
                 for e in data[:60]]
        out = f"Directory listing of {owner}/{repo}/{path}:\n" + "\n".join(lines)
        return True, _secure(out, source=f"github:{owner}/{repo}/{path}")
    # Single file → has 'content' base64-encoded
    if isinstance(data, dict) and data.get("type") == "file":
        try:
            raw = base64.b64decode(data.get("content", "") or "").decode(
                "utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return False, "could not decode file content"
        name = data.get("name", path)
        out = f"File: {name} ({len(raw)} bytes)\n\n{raw[:8000]}"
        return True, _secure(out, source=f"github:{owner}/{repo}/{name}")
    return False, f"unexpected github response shape: {str(data)[:120]}"


def recent_commits(owner: str, repo: str, limit: int = 10) -> tuple[bool, str]:
    """Recent commits in the allowlisted repo."""
    if not _is_allowed(owner, repo):
        return False, (f"I can only read my own repo, not {owner}/{repo}.")
    if not (get_settings().github_token or "").strip():
        return False, "GitHub token not configured."
    limit = max(1, min(int(limit), 30))
    url = f"{_API}/repos/{owner}/{repo}/commits?per_page={limit}"
    try:
        resp = httpx.get(url, headers=_headers(), timeout=30)
    except httpx.HTTPError as exc:
        return False, f"github request failed: {exc}"
    if resp.status_code != 200:
        return False, f"github returned {resp.status_code}"
    items = resp.json()
    if not isinstance(items, list):
        return False, "unexpected response"
    lines = []
    for c in items[:limit]:
        sha = (c.get("sha") or "")[:7]
        msg = (c.get("commit", {}).get("message") or "").splitlines()[0][:80]
        date = (c.get("commit", {}).get("author", {}) or {}).get("date", "")
        lines.append(f"{sha} {date[:10]} {msg}")
    out = f"Recent commits in {owner}/{repo}:\n" + "\n".join(lines)
    return True, _secure(out, source=f"github:{owner}/{repo}/commits")


def mentions_github(message: str) -> bool:
    return "github.com/" in (message or "").lower()
