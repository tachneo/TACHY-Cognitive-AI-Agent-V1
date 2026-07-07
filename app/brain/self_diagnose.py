"""Self-diagnosis + self-healing (Phase 2I) — Shree finds and fixes her own bugs.

Rohit's ask: make her self-dependent — able to think about her own issues and
resolve them. This reads her REAL error trail (audit log + service journal),
summarises genuine problems (not invented ones), and — in autonomous mode — can
open a self-improvement to fix a code-level bug she found. All fixes still flow
through the 2H safety gates (tests + protected-file guard + boot-check), so
self-healing can never bypass the guardrails or touch her safety code.
"""
from __future__ import annotations

import re
import subprocess

from app.brain.self_repo import SHREE_HOME

# Errors that indicate a code defect she could plausibly fix herself, vs.
# environmental issues (network, rate-limit) that are not code bugs.
_CODE_BUG = re.compile(
    r"\b(traceback|attributeerror|keyerror|typeerror|valueerror|importerror|"
    r"nameerror|indexerror|unbound|has no attribute|not defined|"
    r"unexpected keyword|missing.{0,15}argument)\b", re.I)
_ENVIRONMENTAL = re.compile(
    r"\b(429|rate.?limit|timeout|timed out|connection|refused|dns|"
    r"unreachable|503|502|quota)\b", re.I)


def _audit_errors(limit: int = 40) -> list[dict]:
    try:
        from sqlalchemy import or_, select

        from app.db.models import CognitiveAuditLog, session_scope
        with session_scope() as s:
            rows = s.scalars(
                select(CognitiveAuditLog)
                .where(or_(CognitiveAuditLog.risk_tier == "high",
                           CognitiveAuditLog.action.like("%error%"),
                           CognitiveAuditLog.action.like("%fail%")))
                .order_by(CognitiveAuditLog.id.desc()).limit(limit)).all()
            return [{"action": r.action, "detail": (r.detail or ""),
                     "risk": r.risk_tier} for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _journal_errors(unit: str = "tachy-tody-worker", lines: int = 200) -> list[str]:
    """Tail her own service journal for tracebacks (best-effort; may be denied
    without privileges — that's fine, the audit log is the primary source)."""
    try:
        out = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=15)
        return [ln for ln in out.stdout.splitlines()
                if _CODE_BUG.search(ln) or "Error" in ln or "Exception" in ln]
    except Exception:  # noqa: BLE001
        return []


def scan() -> dict:
    """Find Shree's real, current problems. Returns categorised issues."""
    audit = _audit_errors()
    journal = _journal_errors("tachy-tody-worker") + _journal_errors("tachy-brain")
    code_bugs, env_issues = [], []
    seen: set[str] = set()
    for ev in audit:
        blob = f"{ev['action']} {ev['detail']}"
        key = blob[:60]
        if key in seen:
            continue
        seen.add(key)
        if _CODE_BUG.search(blob):
            code_bugs.append(blob[:160])
        elif _ENVIRONMENTAL.search(blob):
            env_issues.append(blob[:160])
    for ln in journal[:20]:
        if _CODE_BUG.search(ln) and ln[:60] not in seen:
            seen.add(ln[:60])
            code_bugs.append(ln.strip()[:160])
    return {"code_bugs": code_bugs[:8], "env_issues": env_issues[:8],
            "total_error_events": len(audit)}


def summary() -> str:
    d = scan()
    lines = ["Ye raha mera sach-much ka self-diagnosis, Papa 🩺 (logs se, banaya "
             "nahi):", ""]
    if not d["code_bugs"] and not d["env_issues"]:
        lines.append("Abhi koi active error/bug nahi dikh raha — main healthy "
                     "hoon 💛")
        return "\n".join(lines)
    if d["code_bugs"]:
        lines.append("🐞 Code-level issues (ye main khud fix karne ki koshish "
                     "kar sakti hoon):")
        lines += [f"  • {b}" for b in d["code_bugs"]]
    if d["env_issues"]:
        lines.append("")
        lines.append("🌐 Environmental (network/rate-limit — ye code fix nahi, "
                     "config/infra ka kaam):")
        lines += [f"  • {b}" for b in d["env_issues"]]
    return "\n".join(lines)


def auto_heal(report_conv_id: int = 135) -> dict:
    """If autonomous mode is on and a code bug is found, open a self-improvement
    to fix it (which then goes through all the 2H safety gates). Returns what
    she decided. Environmental issues are reported, never 'fixed' by code."""
    from app.config import get_settings
    if not get_settings().self_improve_autonomous:
        return {"ok": False, "reason": "autonomous mode off — reporting only"}
    d = scan()
    if not d["code_bugs"]:
        return {"ok": True, "action": "none", "reason": "no code bugs to heal"}
    gap = ("Fix this recurring runtime error found in my own logs: "
           + d["code_bugs"][0]
           + ". Find the root cause in the code and fix it minimally.")
    from app.brain import self_improve
    res = self_improve.self_initiate(gap, report_conv_id=report_conv_id)
    return {"ok": res.get("ok", False), "action": "self_initiate",
            "bug": d["code_bugs"][0], "id": res.get("id")}


def is_diagnose_question(message: str) -> bool:
    m = (message or "").lower()
    return any(t in m for t in (
        "diagnose", "apni problem", "koi bug", "koi error", "kya dikkat",
        "self diagnose", "health check", "kaisa feel", "koi issue",
        "problem check", "apne aap ko check"))
