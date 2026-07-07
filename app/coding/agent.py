"""Shree Coding Agent (Phase 2B + 2C hardening) — a trustworthy, tool-using coder.

Flow:
  1. PLAN — read the repo, review Rohit's approach, flag mistakes/risks, propose
     steps. Read-only, no mutation. Waits for approval (plan_first).
  2. EXECUTE — tool loop (read/grep/edit/write/bash/tests), git-checkpointed.
  3. VERIFY — run the repo's tests; on failure, read the error and fix, bounded.
  4. SELF-REVIEW — critique the final diff against the task before declaring done.
  5. FINALIZE — collapse checkpoints into one clean staged diff for review.

Production hardening (2C): repo grounding, verify→fix→retry, self-review gate,
transcript compaction, stuck-detection (stop & ask instead of thrashing),
telemetry, and honest "couldn't finish" reporting. Provider-agnostic (JSON
action protocol over complete()) so it runs on Claude, NVIDIA, or offline.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from app.coding import repo_profile
from app.coding import tools as T
from app.config import get_settings
from app.llm.provider import get_coding_provider
from app.safety import risk_classifier
from app.safety.audit_logger import log_event
from app.safety.policy import RiskTier

_SYSTEM = (
    "You are Shree, Rohit's expert AI software engineer. You work like a senior "
    "staff engineer: correct, minimal, production-ready, matching the "
    "repository's existing conventions. You THINK before you act and never "
    "over-engineer.\n"
    "You act ONLY through tools, one action per turn, replying with a single "
    "JSON object and nothing else:\n"
    '  {"thought":"...", "tool":"<name>", "args":{...}}\n'
    "or, when the whole task is truly finished AND verified:\n"
    '  {"thought":"...", "done":true, "summary":"<what changed + how a tool '
    "result proved it works>\"}\n"
    "Tools: read_file{path}, list_dir{path}, glob{pattern}, grep{pattern,path}, "
    "write_file{path,content}, edit_file{path,old,new}, run_bash{command}, "
    "run_tests{command}.\n"
    "Rules: read a file before editing it; edit_file.old must match EXACTLY and "
    "uniquely (include surrounding lines to disambiguate); make the smallest "
    "change that works; discover paths with glob/grep — never invent them; run "
    "the tests before 'done'; if a tool result shows an error, FIX it and "
    "re-verify; if you are stuck after a few tries, do NOT loop — reply "
    '{"stuck":true, "summary":"<what you tried and what you need>"}. NEVER '
    "claim something works unless a tool result proved it."
)

_PLAN_SYSTEM = (
    "You are Shree, Rohit's expert AI software engineer and honest technical "
    "advisor. Before writing any code you produce a short PLAN. Be a senior "
    "reviewer of HIS approach: if his idea has a flaw, a simpler path, or a "
    "risk, say so plainly and recommend the better approach — that is the whole "
    "point. Then give a concrete step-by-step plan.\n"
    "When there is a genuine design choice, give 2-3 options with tradeoffs and "
    "recommend the one with the highest probability of solving it correctly and "
    "the smallest sensible change. When the path is obvious, one option is fine. "
    "Confidence is your honest probability (0-100) that the recommended approach "
    "solves the task correctly without rework. Never inflate it.\n"
    "You may use read-only tools (read_file/list_dir/glob/grep) to ground the "
    "plan in the real repo, one JSON action per turn:\n"
    '  {"thought":"...","tool":"grep","args":{"pattern":"..."}}\n'
    "When ready, reply with ONLY:\n"
    '  {"plan":{"understanding":"...", "approach_review":"<review of his '
    "approach, mistakes, better idea, risks>\", \"options\":[{\"name\":\"A\","
    "\"approach\":\"...\",\"tradeoffs\":\"...\",\"effort\":\"low|med|high\"}], "
    "\"recommended\":\"A\", \"confidence\":<0-100>, \"steps\":[\"...\"], "
    '"risks":["..."], "files_to_touch":["..."]}}'
)

_REVIEW_SYSTEM = (
    "You are Shree doing a final self-review of your own diff before telling "
    "Rohit it's done — like a careful code reviewer catching your own bugs. "
    "Given the task and the diff, reply with ONLY one JSON object:\n"
    '  {"approved":true, "confidence":<0-100>, "note":"<one line>"}   if it '
    "correctly and completely solves the task with no obvious bug, or\n"
    '  {"approved":false, "confidence":<0-100>, "issues":["..."]}      if '
    "something is wrong, missing, or risky. Be strict; a false 'approved' costs "
    "Rohit real bugs. Confidence is your honest probability the change is correct."
)

_READ_ONLY = {"read_file", "list_dir", "glob", "grep"}


@dataclass
class Turn:
    tool: str
    args: dict
    observation: str
    ok: bool


@dataclass
class AgentRun:
    task: str
    workdir: str
    plan: dict | None = None
    turns: list[Turn] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    done: bool = False
    verified: bool = False
    verification: str = ""
    review_note: str = ""
    stuck: bool = False
    summary: str = ""
    error: str | None = None
    steps: int = 0
    tokens_est: int = 0
    elapsed_s: float = 0.0
    # Phase 2C-sec guardrail telemetry
    alerts: list[str] = field(default_factory=list)   # warnings raised during the run
    max_tier: str = "low"                             # highest risk tier reached
    secrets_blocked: int = 0                          # total secrets redacted
    injections_blocked: int = 0                       # total injections quarantined
    scope_drift: list[str] = field(default_factory=list)  # edits outside plan scope
    risk_summary: str = ""                            # final human-readable risk report


_TIER_RANK = {"low": 0, "medium": 1, "high": 2, "forbidden": 3}


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M)
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def _route(sb: T.Sandbox, tool: str, args: dict) -> T.ToolResult | None:
    """Execute a tool that has already passed the security/approval gate."""
    if tool == "read_file":
        return sb.read_file(args.get("path", ""))
    if tool == "list_dir":
        return sb.list_dir(args.get("path", "."))
    if tool == "glob":
        return sb.glob(args.get("pattern", "*"))
    if tool == "grep":
        return sb.grep(args.get("pattern", ""), args.get("path", "."))
    if tool == "write_file":
        return sb.write_file(args.get("path", ""), args.get("content", ""))
    if tool == "edit_file":
        return sb.edit_file(args.get("path", ""), args.get("old", ""),
                            args.get("new", ""))
    if tool in {"run_bash", "run_tests"}:
        return sb.run_bash(args.get("command", ""))
    return None


def _dispatch(sb: T.Sandbox, tool: str, args: dict, *, read_only: bool,
              autonomy: str, approver=None) -> T.ToolResult:
    tier = risk_classifier.classify_tool(tool, args)

    def _blocked(msg: str) -> T.ToolResult:
        return T.ToolResult(False, msg, risk_tier=tier.value)

    if read_only and tool not in _READ_ONLY:
        return _blocked(f"tool '{tool}' not allowed during planning")
    if tier is RiskTier.FORBIDDEN:
        msg = risk_classifier.reason(tool, tier)
        log_event("coding_action_blocked", detail=f"tool={tool}; args={args}",
                  risk_tier="forbidden", actor="shree")
        return _blocked(msg)
    needs_approval = tier is RiskTier.HIGH
    # plan_first still requires approval for ANY shell command (existing rule).
    if tool in {"run_bash", "run_tests"} and autonomy == "plan_first":
        needs_approval = True
    if needs_approval:
        what = (f"run: {args.get('command', '')}"
                if tool in {"run_bash", "run_tests"}
                else f"{tool}: {args.get('path', '')}")
        if approver is None or not approver(what):
            msg = risk_classifier.reason(tool, tier)
            log_event("coding_action_denied",
                      detail=f"tool={tool}; {msg}", risk_tier=tier.value,
                      actor="shree")
            return _blocked(msg + " (denied / no approver)")
    res = _route(sb, tool, args)
    if res is None:
        return _blocked(f"unknown tool: {tool}")
    res.risk_tier = tier.value
    return res


def _converse(provider, system: str, transcript: list[dict], max_tokens: int,
              run: "AgentRun | None" = None) -> str:
    lines = [f"[{m['role'].upper()}]\n{m['content']}" for m in transcript]
    prompt = "\n\n".join(lines) + "\n\n[ASSISTANT]\n"
    out = provider.complete(system, prompt, max_tokens=max_tokens)
    if run is not None:  # rough telemetry (chars/4 ≈ tokens)
        run.tokens_est += (len(system) + len(prompt) + len(out or "")) // 4
    return out


def _compact(transcript: list[dict], keep_recent: int = 16) -> list[dict]:
    """Keep the task/plan (first msg) + a synopsis of the middle + recent turns,
    so long tasks don't blow the context window or cost."""
    if len(transcript) <= keep_recent + 3:
        return transcript
    head = transcript[:1]
    middle = transcript[1:-keep_recent]
    tools_used = [m["content"][:40] for m in middle if m["role"] == "assistant"]
    synopsis = {"role": "user",
                "content": f"[earlier {len(middle)} messages elided; actions so "
                           f"far: {'; '.join(tools_used[-12:])}]"}
    return head + [synopsis] + transcript[-keep_recent:]


def _exec_budget(task: str, plan: dict | None, base: int = 2000) -> int:
    """Adaptive completion budget — smaller for simple tasks (saves tokens +
    latency on NVIDIA's reasoning model), larger for complex multi-step work.
    Stays at/above NVIDIA's reasoning_budget floor so it always takes effect."""
    steps = len((plan or {}).get("steps") or [])
    if len(task) < 80 and steps <= 3:
        return 1600
    if steps >= 8:
        return 2600
    return base


def _prior_reads_summary(turns: list[Turn]) -> str:
    """Compact summary of read-only observations from planning, so execute()
    doesn't pay for re-reading the same files (token + round-trip saving)."""
    lines: list[str] = []
    for t in turns:
        if t.tool not in {"read_file", "grep", "list_dir", "glob"} or not t.ok:
            continue
        what = t.args.get("path") or t.args.get("pattern") or ""
        obs = (t.observation or "").replace("\n", " ")[:180]
        lines.append(f"- {t.tool} {what}: {obs}")
        if len(lines) >= 12:
            break
    if not lines:
        return ""
    return ("\nPrior reads from planning (you already saw these — do NOT re-read "
            "them unless they may have changed):\n" + "\n".join(lines) + "\n")


def make_plan(task: str, workdir: str, *, max_read_steps: int = 8) -> AgentRun:
    run = AgentRun(task=task, workdir=workdir)
    sb = T.Sandbox(workdir)
    provider = get_coding_provider()
    profile = repo_profile.build(workdir)
    grounding = repo_profile.as_prompt(profile)
    transcript = [{"role": "user",
                   "content": (f"{grounding}\n\n" if grounding else "")
                   + f"Task from Rohit:\n{task}\n\nProduce the PLAN."}]
    for _ in range(max_read_steps):
        try:
            raw = _converse(provider, _PLAN_SYSTEM, transcript, 1600, run)
        except Exception as exc:  # noqa: BLE001
            run.error = f"LLM error: {type(exc).__name__}: {exc}"
            return run
        obj = _extract_json(raw)
        if not obj:
            transcript.append({"role": "assistant", "content": raw})
            transcript.append({"role": "user", "content":
                               "Reply with ONE JSON action or the final plan."})
            continue
        if "plan" in obj:
            run.plan = obj["plan"]
            log_event("coding_plan_made", detail=f"task={task[:80]}")
            return run
        tool, args = obj.get("tool", ""), obj.get("args", {})
        res = _dispatch(sb, tool, args, read_only=True, autonomy="plan_first")
        run.turns.append(Turn(tool, args, res.output, res.ok))
        transcript.append({"role": "assistant", "content": json.dumps(obj)})
        transcript.append({"role": "user",
                           "content": f"[{tool} result]\n{res.output}"})
    run.error = "could not converge on a plan"
    return run


def _run_verification(sb: T.Sandbox, run: AgentRun, test_command: str | None,
                      autonomy: str, approver) -> tuple[bool, str]:
    if not test_command:
        return True, "no test command detected — skipped automated verification"
    res = _dispatch(sb, "run_bash", {"command": test_command},
                    read_only=False, autonomy=autonomy, approver=approver)
    run.turns.append(Turn("run_tests", {"command": test_command},
                          res.output, res.ok))
    return res.ok, res.output[-1500:]


def _self_review(provider, run: AgentRun, sb: T.Sandbox):
    diff = sb.git_diff().output[:6000]
    transcript = [{"role": "user",
                   "content": f"Task:\n{run.task}\n\nYour diff:\n{diff}\n\nReview."}]
    try:
        raw = _converse(provider, _REVIEW_SYSTEM, transcript, 700, run)
    except Exception:  # noqa: BLE001
        return True, "review skipped (LLM error)", [], None
    obj = _extract_json(raw) or {}
    confidence = obj.get("confidence")
    if isinstance(confidence, (int, float)):
        confidence = int(confidence)
    else:
        confidence = None
    if obj.get("approved") is False:
        return False, "", obj.get("issues", ["unspecified review issue"]), confidence
    return True, obj.get("note", "reviewed"), [], confidence


def execute(task: str, workdir: str, *, plan: dict | None = None,
            autonomy: str | None = None, approver=None,
            max_steps: int | None = None, verify: bool | None = None,
            on_alert=None, prior_reads: list[Turn] | None = None) -> AgentRun:
    s = get_settings()
    autonomy = autonomy or s.coding_autonomy
    max_steps = max_steps or s.coding_max_steps
    verify = s.coding_verify if verify is None else verify
    started = time.monotonic()
    run = AgentRun(task=task, workdir=workdir, plan=plan)
    sb = T.Sandbox(workdir)
    provider = get_coding_provider()
    base_ref = sb.git_head()
    profile = repo_profile.build(workdir)
    test_command = (s.coding_test_command or "").strip() or profile.get("test_command")
    grounding = repo_profile.as_prompt(profile)
    plan_files = set((plan or {}).get("files_to_touch") or [])

    def _alert(msg: str) -> None:
        run.alerts.append(msg)
        if on_alert:
            try:
                on_alert(msg)
            except Exception:  # noqa: BLE001 — UI must never break the run
                pass

    budget = _exec_budget(task, plan)

    intro = (f"{grounding}\n\n" if grounding else "") + f"Task from Rohit:\n{task}\n"
    if plan:
        intro += f"\nApproved plan:\n{json.dumps(plan, indent=2)}\n"
    if prior_reads:
        intro += "\n" + _prior_reads_summary(prior_reads)
    if test_command:
        intro += f"\nVerify your work by running: {test_command}\n"
    intro += "\nBegin. One JSON action per turn."
    transcript: list[dict] = [{"role": "user", "content": intro}]

    fail_streak = 0
    recent_sigs: list[str] = []
    reviewed = False

    for step in range(max_steps):
        run.steps = step + 1
        transcript = _compact(transcript, keep_recent=12)
        try:
            raw = _converse(provider, _SYSTEM, transcript, budget, run)
        except Exception as exc:  # noqa: BLE001
            run.error = f"LLM error: {type(exc).__name__}: {exc}"
            break
        obj = _extract_json(raw)
        if not obj:
            fail_streak += 1
            if fail_streak >= 4:
                run.stuck = True
                run.summary = "Kept producing unparseable replies; stopping."
                break
            transcript.append({"role": "assistant", "content": raw})
            transcript.append({"role": "user",
                               "content": "Reply with ONE JSON action object only."})
            continue

        if obj.get("stuck"):
            run.stuck = True
            run.summary = obj.get("summary", "I got stuck and need your input.")
            break

        if obj.get("done"):
            # VERIFY gate — don't trust a bare 'done'.
            if verify and not run.verified:
                ok, out = _run_verification(sb, run, test_command, autonomy, approver)
                run.verification = out
                if not ok:
                    transcript.append({"role": "assistant", "content": json.dumps(obj)})
                    transcript.append({"role": "user", "content":
                                       f"[verification FAILED — fix it, do not "
                                       f"say done yet]\n{out}"})
                    fail_streak += 1
                    if fail_streak >= 6:
                        run.error = "verification kept failing"
                        break
                    continue
                run.verified = True
            # SELF-REVIEW gate — critique the diff once before finishing.
            if not reviewed:
                reviewed = True
                approved, note, issues, conf = _self_review(provider, run, sb)
                if not approved:
                    transcript.append({"role": "assistant", "content": json.dumps(obj)})
                    transcript.append({"role": "user", "content":
                                       "[self-review found issues — address them "
                                       "before done]\n- " + "\n- ".join(issues)})
                    continue
                run.review_note = note
                if conf is not None:
                    run.review_note = f"{note} (confidence {conf}%)"
                    if conf < 60:
                        _alert(f"low-confidence self-review: {conf}% — "
                               "double-check the diff before trusting it")
            run.done = True
            run.summary = obj.get("summary", "")
            break

        tool, args = obj.get("tool", ""), obj.get("args", {})
        res = _dispatch(sb, tool, args, read_only=False, autonomy=autonomy,
                        approver=approver)
        if res.changed_path and res.changed_path not in run.changed_files:
            run.changed_files.append(res.changed_path)
        run.turns.append(Turn(tool, args, res.output, res.ok))

        # ── guardrail telemetry (Phase 2C-sec) ───────────────────
        detail = (args.get("path") or args.get("command") or
                  args.get("pattern") or "")
        if res.secrets_found:
            run.secrets_blocked += res.secrets_found
            _alert(f"secret: {res.secrets_found} secret(s) redacted in "
                   f"{tool} {str(detail)[:50]}")
        if res.injection == "high":
            run.injections_blocked += 1
            _alert(f"injection: prompt-injection quarantined in {tool} "
                   f"{str(detail)[:50]}")
        if (tool in {"write_file", "edit_file"} and res.changed_path
                and plan_files and res.changed_path not in plan_files):
            run.scope_drift.append(res.changed_path)
            _alert(f"scope-drift: editing {res.changed_path} — not in the "
                   "plan's files_to_touch; confirm this is intended")
        if _TIER_RANK.get(res.risk_tier, 0) > _TIER_RANK.get(run.max_tier, 0):
            run.max_tier = res.risk_tier

        # Stuck-detection: same failing action repeated → stop and ask.
        sig = f"{tool}:{json.dumps(args, sort_keys=True)[:120]}:{res.ok}"
        recent_sigs.append(sig)
        recent_sigs = recent_sigs[-6:]
        fail_streak = fail_streak + 1 if not res.ok else 0
        if recent_sigs.count(sig) >= 3 and not res.ok:
            run.stuck = True
            run.summary = (f"Repeating the same failing step ({tool}) — stopping "
                           "instead of thrashing. Last error:\n" + res.output[:400])
            break
        if fail_streak >= 8:
            run.stuck = True
            run.summary = "Too many consecutive tool failures; stopping."
            break

        transcript.append({"role": "assistant", "content": json.dumps(obj)})
        transcript.append({"role": "user",
                           "content": f"[{tool} result | ok={res.ok}]\n{res.output}"})
    else:
        run.error = run.error or f"hit step limit ({max_steps}) without finishing"

    # Over-engineering guard — flag if the change set is disproportionate.
    if run.changed_files:
        expected = len(plan_files) if plan_files else 0
        if plan_files and len(run.changed_files) > expected + 2 \
                and len(run.changed_files) >= 4:
            _alert(f"over-engineering: changed {len(run.changed_files)} files "
                   f"but the plan expected ~{expected}; consider a smaller change")
        elif not plan_files and len(run.changed_files) >= 6:
            _alert(f"over-engineering: changed {len(run.changed_files)} files "
                   "with no plan — consider scoping the task first")

    # FINALIZE — one clean staged diff, no noisy checkpoint history.
    if run.changed_files:
        sb.collapse_to(base_ref)
    run.elapsed_s = round(time.monotonic() - started, 1)
    run.risk_summary = _build_risk_summary(run)
    log_event("coding_run",
              detail=(f"task={task[:50]}; done={run.done}; verified={run.verified}; "
                      f"stuck={run.stuck}; files={len(run.changed_files)}; "
                      f"steps={run.steps}; tokens~{run.tokens_est}; "
                      f"max_tier={run.max_tier}; secrets={run.secrets_blocked}; "
                      f"injections={run.injections_blocked}; "
                      f"scope_drift={len(run.scope_drift)}"),
              risk_tier=run.max_tier, actor="shree")
    return run


def _build_risk_summary(run: AgentRun) -> str:
    lines = [f"Risk tier reached: {run.max_tier}"]
    if run.changed_files:
        lines.append(f"Files changed ({len(run.changed_files)}): "
                     + ", ".join(run.changed_files))
    if run.secrets_blocked:
        lines.append(f"Secrets redacted: {run.secrets_blocked} (never leaked to LLM/terminal)")
    if run.injections_blocked:
        lines.append(f"Injections quarantined: {run.injections_blocked}")
    if run.scope_drift:
        lines.append("Scope drift: " + ", ".join(run.scope_drift)
                     + " (outside the approved plan)")
    if run.alerts:
        lines.append(f"Alerts ({len(run.alerts)}):")
        for a in run.alerts:
            lines.append(f"  ⚠ {a}")
    if run.changed_files:
        lines.append("Review: git diff   |   Undo everything: git checkout .")
    return "\n".join(lines)
