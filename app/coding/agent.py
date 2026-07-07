"""Shree Coding Agent (Phase 2B) — a real tool-using, plan-first coder.

Flow (matches Rohit's asks):
  1. PLAN — Shree first reads enough of the repo, reviews HIS approach, flags
     mistakes/risks, and proposes a step-by-step plan. She stops and waits for
     approval (plan_first autonomy). This is "correct my mistakes before you
     implement."
  2. EXECUTE — after approval she runs a tool loop (read/grep/edit/write/bash/
     tests) until the task is done, taking a git checkpoint before each edit.
  3. REVIEW — she runs tests and reports honestly what changed.

Provider-agnostic: the model speaks a small JSON action protocol over the
plain ``complete()`` interface, so it works on Claude, NVIDIA, or offline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.coding import tools as T
from app.config import get_settings
from app.llm.provider import get_coding_provider
from app.safety.audit_logger import log_event

_SYSTEM = (
    "You are Shree, Rohit's expert AI software engineer. You work like a senior "
    "staff engineer: correct, minimal, production-ready, matching the "
    "repository's existing conventions. You THINK before you act, question a "
    "flawed approach, and never over-engineer.\n"
    "You act ONLY through tools, one action per turn, by replying with a single "
    "JSON object and nothing else:\n"
    '  {"thought": "...", "tool": "<name>", "args": {...}}\n'
    "or, when the whole task is finished:\n"
    '  {"thought": "...", "done": true, "summary": "<what changed + how you '
    "verified it>\"}\n"
    "Tools: read_file{path}, list_dir{path}, glob{pattern}, grep{pattern,path}, "
    "write_file{path,content}, edit_file{path,old,new}, run_bash{command}, "
    "run_tests{command}.\n"
    "Rules: read a file before editing it; edit_file.old must match EXACTLY and "
    "uniquely; make the smallest change that works; run the tests before saying "
    "done; never invent file paths — discover them with glob/grep; do not claim "
    "something works unless a tool result proved it."
)

_PLAN_SYSTEM = (
    "You are Shree, Rohit's expert AI software engineer and honest technical "
    "advisor. Before writing any code you produce a short PLAN. Be a senior "
    "reviewer of HIS approach: if his idea has a flaw, a simpler path, or a "
    "risk, say so plainly and recommend the better approach — this is the whole "
    "point. Then give a concrete step-by-step plan.\n"
    "You may use read-only tools (read_file/list_dir/glob/grep) to ground the "
    "plan in the real repo, one JSON action per turn:\n"
    '  {"thought":"...","tool":"grep","args":{"pattern":"..."}}\n'
    "When ready, reply with ONLY:\n"
    '  {"plan": {"understanding":"...", "approach_review":"<review of his '
    "approach, mistakes, better idea, risks>\", \"steps\":[\"...\"], "
    '"risks":["..."], "files_to_touch":["..."]}}'
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
    summary: str = ""
    error: str | None = None


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply (tolerates prose/fences)."""
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


def _dispatch(sb: T.Sandbox, tool: str, args: dict, *, read_only: bool,
              autonomy: str, approver=None) -> T.ToolResult:
    if read_only and tool not in _READ_ONLY:
        return T.ToolResult(False, f"tool '{tool}' not allowed during planning")
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
        cmd = args.get("command", "")
        if T.is_destructive(cmd) or autonomy == "plan_first":
            if approver is None or not approver(f"run: {cmd}"):
                return T.ToolResult(False, "command needs approval (denied/"
                                           "no approver)")
        return sb.run_bash(cmd)
    return T.ToolResult(False, f"unknown tool: {tool}")


def _converse(provider, system: str, transcript: list[dict], max_tokens: int) -> str:
    """Render the running transcript into one prompt for the complete() API."""
    lines = []
    for m in transcript:
        lines.append(f"[{m['role'].upper()}]\n{m['content']}")
    prompt = "\n\n".join(lines) + "\n\n[ASSISTANT]\n"
    return provider.complete(system, prompt, max_tokens=max_tokens)


def make_plan(task: str, workdir: str, *, max_read_steps: int = 8) -> AgentRun:
    """Produce a plan + approach review WITHOUT changing anything."""
    run = AgentRun(task=task, workdir=workdir)
    sb = T.Sandbox(workdir)
    provider = get_coding_provider()
    transcript = [{"role": "user",
                   "content": f"Task from Rohit:\n{task}\n\nProduce the PLAN."}]
    for _ in range(max_read_steps):
        try:
            raw = _converse(provider, _PLAN_SYSTEM, transcript, 1600)
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


def execute(task: str, workdir: str, *, plan: dict | None = None,
            autonomy: str | None = None, approver=None,
            max_steps: int | None = None) -> AgentRun:
    """Run the full tool loop to complete the task (post-approval)."""
    s = get_settings()
    autonomy = autonomy or s.coding_autonomy
    max_steps = max_steps or s.coding_max_steps
    run = AgentRun(task=task, workdir=workdir, plan=plan)
    sb = T.Sandbox(workdir)
    provider = get_coding_provider()

    intro = f"Task from Rohit:\n{task}\n"
    if plan:
        intro += f"\nApproved plan:\n{json.dumps(plan, indent=2)}\n"
    intro += "\nBegin. One JSON action per turn."
    transcript = [{"role": "user", "content": intro}]

    for _ in range(max_steps):
        try:
            raw = _converse(provider, _SYSTEM, transcript, 2000)
        except Exception as exc:  # noqa: BLE001
            run.error = f"LLM error: {type(exc).__name__}: {exc}"
            return run
        obj = _extract_json(raw)
        if not obj:
            transcript.append({"role": "assistant", "content": raw})
            transcript.append({"role": "user", "content":
                               "Reply with ONE JSON action object only."})
            continue
        if obj.get("done"):
            run.done = True
            run.summary = obj.get("summary", "")
            log_event("coding_done",
                      detail=f"task={task[:60]}; files={run.changed_files}")
            return run
        tool, args = obj.get("tool", ""), obj.get("args", {})
        res = _dispatch(sb, tool, args, read_only=False, autonomy=autonomy,
                        approver=approver)
        if res.changed_path and res.changed_path not in run.changed_files:
            run.changed_files.append(res.changed_path)
        run.turns.append(Turn(tool, args, res.output, res.ok))
        transcript.append({"role": "assistant", "content": json.dumps(obj)})
        transcript.append({"role": "user",
                           "content": f"[{tool} result | ok={res.ok}]\n"
                                      f"{res.output}"})
    run.error = f"hit step limit ({max_steps}) without finishing"
    return run
