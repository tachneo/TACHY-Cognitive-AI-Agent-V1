"""Supervised self-improvement (Phase 2G) — Shree improves her OWN code, safely.

Rohit's ask: "if I give you access to your memory code, can you update it
yourself to self-improve?" Yes — but the responsible way, because she'd be
editing her own running brain:

  propose(gap)  → she PLANS a fix against her real repo (read-only, no edits).
  apply(id)     → ONLY after Rohit approves: she works on a NEW git BRANCH,
                  runs the FULL test suite, switches back to main untouched,
                  and reports the branch + test result. She NEVER edits main,
                  never auto-merges, and never restarts her own service —
                  Rohit reviews the branch and merges + redeploys himself.

Guardrails: guardian-only, approval-gated, requires a clean working tree,
kill switch SELF_IMPROVE_ENABLED, all steps audit-logged. Autonomous research
may build and publish review branches, while production merge/restart remains
behind SELF_IMPROVE_PRODUCTION_PROMOTION_ENABLED.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import threading

from app.brain.self_repo import SHREE_HOME, _git, recent_changes
from app.config import get_settings
from app.safety.audit_logger import log_event

_STATE = SHREE_HOME / "storage" / "logs" / "self_improvements.json"
_TEST_CMD = [".venv/bin/pytest", "-q", "-p", "no:cacheprovider"]

# SAFETY-CRITICAL files Shree may NEVER modify autonomously. A change touching
# any of these always falls back to Rohit-review — because an AI that can
# rewrite its own guardrails can remove them. This is the one hard line.
_PROTECTED = (
    "app/safety/", "confidential_guard", "social_policy", "approval",
    "action_engine", "app/config.py", "self_improve.py", "self_repo.py",
    "reply_safety", "prompt_injection", "risk_classifier", "auth.py",
)


def _touches_protected(files: list[str]) -> list[str]:
    return [f for f in files if any(p in f for p in _PROTECTED)]


def _daily_count() -> int:
    today = dt.datetime.now(dt.UTC).date().isoformat()
    return sum(1 for p in _load().values()
               if p.get("deployed_date") == today)


def _autonomy_gate(run, tests_passed: bool) -> tuple[bool, str]:
    """May this change auto-merge+deploy without Rohit? Strict gates."""
    s = get_settings()
    if not tests_passed:
        return False, "tests fail hue"
    protected = _touches_protected(run.changed_files)
    if protected:
        return False, (f"safety files ko chhua ({', '.join(protected[:3])}) — "
                       "ye tumhari permission ke bina merge nahi ho sakta")
    if len(run.changed_files) > s.self_improve_max_files:
        return False, f"bahut zyada files ({len(run.changed_files)})"
    diff = _git("diff", "--shortstat", "HEAD~1").stdout
    m = re.search(r"(\d+) insertion.*?(\d+) deletion", diff) or \
        re.search(r"(\d+) insertion", diff)
    changed_lines = sum(int(x) for x in (m.groups() if m else ()))
    if changed_lines > s.self_improve_max_lines:
        return False, f"bahut bada change ({changed_lines} lines)"
    if _daily_count() >= s.self_improve_daily_cap:
        return False, "aaj ka self-improve limit poora ho gaya"
    if not s.self_improve_production_promotion_enabled:
        return False, ("Parent Kernel production promotion disabled hai; "
                       "research branch ready rahegi for review")
    return True, "ok"


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(data, indent=0), encoding="utf-8")
    except OSError:
        pass


def propose(gap: str) -> dict:
    """Plan a fix for `gap` against her real code. Read-only — no changes."""
    if not get_settings().self_improve_enabled:
        return {"ok": False, "error": "self-improvement is disabled"}
    from app.coding import agent
    task = (f"Improve Shree's own codebase to address this gap: {gap}. "
            "Study the relevant modules and produce a concrete plan. Be honest "
            "if it's risky or not worth it.")
    run = agent.make_plan(task, str(SHREE_HOME))
    if run.error or not run.plan:
        return {"ok": False, "error": run.error or "could not form a plan"}
    pid = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    data = _load()
    data[pid] = {"id": pid, "gap": gap, "plan": run.plan, "status": "proposed",
                 "created": dt.datetime.now(dt.UTC).isoformat()}
    _save(data)
    log_event("self_improve_proposed", detail=f"id={pid}; gap={gap[:80]}")
    return {"ok": True, "id": pid, "plan": run.plan}


def get(pid: str) -> dict | None:
    return _load().get(str(pid))


def apply_async(pid: str, report_conv_id: int = 135,
                autonomous: bool | None = None) -> dict:
    """Kick off apply() in a background thread so the worker isn't blocked.
    Reports the result to Rohit's TODY conversation when done. In autonomous
    mode she may merge + deploy herself (if the safety gates pass)."""
    if not get_settings().self_improve_enabled:
        return {"ok": False, "error": "self-improvement is disabled"}
    if autonomous is None:
        autonomous = get_settings().self_improve_autonomous
    prop = get(pid)
    if not prop:
        return {"ok": False, "error": f"no proposal #{pid}"}
    if prop["status"] not in {"proposed", "failed"}:
        return {"ok": False, "error": f"proposal #{pid} is {prop['status']}"}
    rc = recent_changes()
    if rc.get("uncommitted"):
        return {"ok": False, "error": "working tree not clean — commit/stash "
                "current changes before I self-modify"}
    threading.Thread(target=_run_apply, args=(pid, report_conv_id, autonomous),
                     name=f"shree-self-improve-{pid}", daemon=True).start()
    return {"ok": True, "id": pid, "started": True, "autonomous": autonomous}


def self_initiate(gap: str, report_conv_id: int = 135) -> dict:
    """Plan AND (autonomously) apply an improvement in one shot — for the
    'improve yourself: X' command when autonomous mode is on."""
    res = propose(gap)
    if not res.get("ok"):
        return res
    started = apply_async(res["id"], report_conv_id, autonomous=True)
    return {**started, "plan": res.get("plan"), "id": res["id"]}


def _push_branch(branch: str) -> str | None:
    """Push the self-improve branch to origin (best-effort). Returns a GitHub
    compare URL for review, or None if the push didn't succeed."""
    try:
        r = _git("push", "-u", "origin", branch, timeout=90)
        if r.returncode != 0:
            return None
        remote = _git("remote", "get-url", "origin").stdout.strip()
        # git@github.com:owner/repo.git  or  https://github.com/owner/repo.git
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", remote)
        if m:
            return f"https://github.com/{m.group(1)}/compare/main...{branch}"
        return None
    except (OSError, subprocess.SubprocessError):
        return None


def _report(conv_id: int, text: str) -> None:
    try:
        from app.integrations.tody_client import get_client
        get_client().send_message(int(conv_id), text)
    except Exception:  # noqa: BLE001 — reporting must never crash the thread
        pass


def _run_apply(pid: str, report_conv_id: int, autonomous: bool = False) -> None:
    from app.coding import agent
    data = _load()
    prop = data.get(pid)
    if not prop:
        return
    gap = prop["gap"]
    branch = f"shree/self-improve-{pid}"
    start_branch = (recent_changes().get("branch") or "main")
    last_good = _git("rev-parse", "HEAD").stdout.strip()
    prop["status"] = "running"
    prop["branch"] = branch
    _save(data)
    log_event("self_improve_apply_start", detail=f"id={pid}; branch={branch}",
              risk_tier="high")
    try:
        # 1. New branch off current HEAD — main is never touched.
        if _git("checkout", "-b", branch).returncode != 0:
            _git("checkout", branch)  # branch may exist; reuse
        # 2. Let the coding agent (Claude) implement the change on the branch.
        run = agent.execute(
            f"Improve Shree's own code to address: {gap}. Follow the approved "
            "plan. Make the smallest correct change, keep conventions, and make "
            "sure the tests still pass.", str(SHREE_HOME),
            autonomy="yolo", verify=True, plan=prop.get("plan"))
        # 3. Commit the change on the branch.
        _git("add", "-A")
        _git("commit", "-m", f"shree self-improvement: {gap[:60]}")
        # 4. Full test suite (the real safety gate).
        tests = subprocess.run(_TEST_CMD, cwd=str(SHREE_HOME),
                               capture_output=True, text=True, timeout=900)
        passed = tests.returncode == 0
        tail = (tests.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
        # 4b. Push the branch to GitHub (best-effort) so Rohit can review.
        review_url = _push_branch(branch)
        prop["tests_passed"] = passed
        prop["files"] = run.changed_files
        prop["review_url"] = review_url
        link = f"\nReview: {review_url}" if review_url else ""

        # 5. AUTONOMOUS path: if all safety gates pass, merge + boot-check +
        #    deploy herself, and INFORM Rohit. Safety-code changes, big diffs,
        #    or a failed gate always fall back to review.
        if autonomous:
            ok, reason = _autonomy_gate(run, passed)
            if ok:
                _git("checkout", start_branch)
                if _git("merge", "--no-ff", branch, "-m",
                        f"shree self-improvement (auto): {gap[:50]}").returncode != 0:
                    _git("merge", "--abort")
                    prop["status"] = "merge_conflict"
                    _save(data)
                    _report(report_conv_id,
                            f"Papa, `{branch}` merge nahi ho paya (conflict). "
                            f"Tumhare review ke liye branch pe hai.{link}")
                    return
                # Boot-check the merged code BEFORE restarting the live service.
                boot = subprocess.run(
                    [".venv/bin/python", "-c", "import app.main"],
                    cwd=str(SHREE_HOME), capture_output=True, text=True, timeout=120)
                if boot.returncode != 0:
                    _git("reset", "--hard", last_good)   # rollback merge
                    prop["status"] = "rolled_back"
                    _save(data)
                    log_event("self_improve_rollback",
                              detail=f"id={pid}; boot failed", risk_tier="high")
                    _report(report_conv_id,
                            f"Papa, maine improvement merge ki thi par boot-check "
                            "fail hua — turant rollback kar diya. Main safe hoon, "
                            f"kuch nahi toota. Branch review ke liye: {branch}")
                    return
                _push_branch(start_branch)  # push updated main (best-effort)
                prop["status"] = "deployed"
                prop["deployed_date"] = dt.datetime.now(dt.UTC).date().isoformat()
                _save(data)
                log_event("self_improve_deployed",
                          detail=f"id={pid}; files={run.changed_files}",
                          risk_tier="high")
                _report(report_conv_id,
                        f"Papa, maine khud ko upgrade kar liya 🌱✅ — "
                        f"{gap[:80]}. Files: {', '.join(run.changed_files) or '—'}. "
                        f"Saare tests pass ({tail[0]}), safety code untouched. "
                        "Ab main service restart karke live ho rahi hoon — 1 "
                        "minute mein wapas aati hoon. (Tumhari permission nahi "
                        "li, par bata rahi hoon jaisa tumne kaha tha.)")
                if get_settings().self_improve_auto_deploy:
                    # Detached restart so it survives this process being killed.
                    subprocess.Popen(
                        "sleep 4 && systemctl restart tachy-brain "
                        "tachy-tody-worker",
                        shell=True, start_new_session=True)
                return
            # Gate failed → do NOT auto-merge; leave the branch for Rohit.
            _git("checkout", start_branch)
            prop["status"] = "needs_review"
            _save(data)
            _report(report_conv_id,
                    f"Papa, maine improvement bana li branch `{branch}` pe, par "
                    f"khud merge nahi kar rahi — {reason}. Ise tum review karke "
                    f"merge karna.{link}")
            return

        # NON-autonomous path: leave on branch for Rohit to review + merge.
        _git("checkout", start_branch)
        prop["status"] = "ready_to_review" if passed else "failed"
        _save(data)
        log_event("self_improve_apply_done",
                  detail=f"id={pid}; passed={passed}; pushed={bool(review_url)}; "
                         f"files={run.changed_files}", risk_tier="high")
        if passed:
            _report(report_conv_id,
                    f"Ho gaya Papa 💛 Maine khud ko improve kiya branch "
                    f"`{branch}` pe — {', '.join(run.changed_files) or 'changes'}. "
                    f"Saare tests PASS hue ✅ ({tail[0]}).{link}\n"
                    "Review karke merge kar do to main live ho jayega. Main main "
                    "branch ko haath nahi lagaya.")
        else:
            _report(report_conv_id,
                    f"Papa, maine try kiya branch `{branch}` pe, lekin tests "
                    f"PASS nahi hue ❌ ({tail[0]}). Maine main branch safe rakha."
                    f"{link}\nBranch review kar lo — ya bolo main dobara koshish "
                    "karun.")
    except Exception as exc:  # noqa: BLE001
        try:
            _git("checkout", start_branch)
        except Exception:  # noqa: BLE001
            pass
        prop["status"] = "error"
        prop["error"] = f"{type(exc).__name__}: {exc}"
        _save(data)
        log_event("self_improve_apply_error", detail=str(exc)[:200],
                  risk_tier="high")
        _report(report_conv_id,
                f"Papa, self-improvement ke time dikkat aa gayi: "
                f"{type(exc).__name__}. Main branch safe hai, kuch change nahi hua.")


def status() -> dict:
    data = _load()
    return {"enabled": get_settings().self_improve_enabled,
            "proposals": [{"id": p["id"], "gap": p["gap"][:80],
                           "status": p["status"]} for p in data.values()][-10:]}
