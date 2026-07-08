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
    """Find Shree's real, current problems. Returns categorised issues —
    runtime tracebacks (audit + journal) AND the repair queue's ready
    signatures, so behavioral failures she noticed herself become repair
    candidates, not just crashes."""
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
    # The metacognitive link: her OWN accumulated noticing (repair queue).
    try:
        from app.brain import repair_queue
        behavioral = repair_queue.ready(limit=8)
    except Exception:  # noqa: BLE001
        behavioral = []
    for r in behavioral:
        if r.get("fix_class") == "code":
            code_bugs.append(
                f"repair-queue:{r['signature']} (seen {r['recurrence']}x) — "
                f"{(r.get('sample') or '')[:80]}")
    return {"code_bugs": code_bugs[:8], "env_issues": env_issues[:8],
            "behavioral": behavioral,
            "total_error_events": len(audit)}


def summary() -> str:
    d = scan()
    lines = ["Ye raha mera sach-much ka self-diagnosis, Papa 🩺 (logs se, banaya "
             "nahi):", ""]
    if not d["code_bugs"] and not d["env_issues"] and not d.get("behavioral"):
        lines.append("Abhi koi active error/bug nahi dikh raha — main healthy "
                     "hoon 💛")
        return "\n".join(lines)
    if d.get("behavioral"):
        lines.append("🔁 Mere repeated behavioral failures (repair queue, "
                     "evidence-based):")
        lines += [f"  • {r['signature']} — {r['recurrence']}x dekha, "
                  f"fix type: {r['fix_class']}" for r in d["behavioral"]]
        lines.append("")
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
    # Prefer a repair-queue signature (HER OWN noticing, evidence-tiered) over
    # a raw log line — and drive its status through the queue lifecycle so the
    # one-fix-per-signature rule holds.
    signature = None
    target = d["code_bugs"][0]
    for r in d.get("behavioral", []):
        if r.get("fix_class") == "code":
            signature = r["signature"]
            target = (f"recurring failure signature '{r['signature']}' "
                      f"(seen {r['recurrence']}x, evidence tier {r['tier']}): "
                      f"{(r.get('sample') or '')[:200]}")
            break
    from app.brain import repair_queue, self_improve
    if signature:
        repair_queue.mark(signature, status="repairing")
    gap = ("Fix this recurring problem found in my own logs/repair queue: "
           + target
           + ". Find the root cause in the code and fix it minimally.")
    res = self_improve.self_initiate(gap, report_conv_id=report_conv_id)
    if signature:
        if res.get("ok"):
            repair_queue.mark(signature, status="fixed",
                              note=f"self_improve id={res.get('id')}")
        else:
            repair_queue.mark(signature, status="ready",
                              note=f"self_initiate failed: {res.get('reason', '')[:100]}")
    return {"ok": res.get("ok", False), "action": "self_initiate",
            "bug": target[:160], "signature": signature, "id": res.get("id")}


def is_diagnose_question(message: str) -> bool:
    m = (message or "").lower()
    return any(t in m for t in (
        "diagnose", "apni problem", "koi bug", "koi error", "kya dikkat",
        "self diagnose", "health check", "kaisa feel", "koi issue",
        "problem check", "apne aap ko check"))
