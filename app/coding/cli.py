"""`shree` — Shree's coding agent in your terminal (Phase 2B).

Usage:
    shree "add rate limiting to the login endpoint"   # plan → approve → do
    shree                                              # interactive REPL
    shree --plan "refactor the fee module"             # plan only, no changes
    shree --auto "fix the failing test"                # auto low-risk edits
    shree --yolo "..."                                 # execute without asking

By default it is PLAN-FIRST: Shree reviews your approach, flags mistakes, and
waits for your OK before touching any file. Runs locally in the current repo;
your code stays on your machine.
"""
from __future__ import annotations

import argparse
import os
import sys

from app.coding import agent

# ANSI colours (skip when not a tty)
_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _bold(t): return _c("1", t)
def _dim(t): return _c("2", t)
def _green(t): return _c("32", t)
def _yellow(t): return _c("33", t)
def _cyan(t): return _c("36", t)
def _red(t): return _c("31", t)


def _print_plan(plan: dict) -> None:
    print(_bold("\n🧠 Shree's plan\n"))
    if plan.get("understanding"):
        print(_cyan("Understanding: ") + plan["understanding"] + "\n")
    if plan.get("approach_review"):
        print(_yellow("Review of your approach:\n") + plan["approach_review"] + "\n")
    if plan.get("steps"):
        print(_cyan("Steps:"))
        for i, s in enumerate(plan["steps"], 1):
            print(f"  {i}. {s}")
        print()
    if plan.get("risks"):
        print(_red("Risks:"))
        for r in plan["risks"]:
            print(f"  ⚠ {r}")
        print()
    if plan.get("files_to_touch"):
        print(_dim("Files: " + ", ".join(plan["files_to_touch"])) + "\n")


def _ask(prompt: str) -> bool:
    try:
        return input(_bold(prompt + " [y/N] ")).strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def _approver(what: str) -> bool:
    return _ask(f"Allow → {what}?")


def _run_task(task: str, workdir: str, autonomy: str, plan_only: bool) -> int:
    print(_dim(f"repo: {workdir}"))
    print(_dim("thinking about your approach…"))
    planned = agent.make_plan(task, workdir)
    if planned.error:
        print(_red(f"✗ {planned.error}"))
        return 1
    if planned.plan:
        _print_plan(planned.plan)
    if plan_only:
        return 0
    if autonomy == "plan_first" and not _ask("Proceed with implementation?"):
        print(_dim("Okay — nothing changed. Tell me how to adjust the plan."))
        return 0

    def _on_alert(msg: str) -> None:
        print(_red(f"  ⚠ {msg}"))

    print(_dim("\nworking…\n"))
    run = agent.execute(task, workdir, plan=planned.plan, autonomy=autonomy,
                        approver=_approver, on_alert=_on_alert)
    for t in run.turns:
        mark = _green("✓") if t.ok else _red("✗")
        detail = t.args.get("path") or t.args.get("command") \
            or t.args.get("pattern") or ""
        print(f"  {mark} {t.tool} {_dim(str(detail)[:70])}")
    print()
    if run.stuck:
        print(_yellow("⏸ Shree paused (stuck) — she stopped instead of "
                      "thrashing:"))
        print("  " + run.summary)
        return 2
    if run.error:
        print(_red(f"✗ {run.error}"))
    if run.verified:
        print(_green("✓ tests passed") + _dim(f"  ({run.review_note})"))
    elif run.verification:
        print(_yellow("⚠ verification: ") + run.verification.splitlines()[-1][:120])
    if run.changed_files:
        print(_green("Changed: ") + ", ".join(run.changed_files))
    if run.summary:
        print(_bold("\n" + run.summary))
    # Risk summary — always show when something notable happened.
    if run.alerts or run.max_tier != "low" or run.scope_drift \
            or run.secrets_blocked or run.injections_blocked:
        print(_yellow("\n⚠ Shree's risk report:"))
        for line in run.risk_summary.splitlines():
            print("  " + (_red(line) if line.startswith("  ⚠") else _dim(line)))
    print(_dim(f"\n{run.steps} steps · ~{run.tokens_est} tokens · {run.elapsed_s}s"
               f" · max-tier={run.max_tier}"))
    if run.changed_files and not (run.alerts or run.max_tier != "low"):
        print(_dim("Review: git diff   |   Undo everything: git checkout ."))
    return 0 if run.done else 1


def _repl(workdir: str, autonomy: str) -> int:
    print(_bold("Shree coding agent") + _dim(f"  ({workdir})"))
    print(_dim("Type a coding task, or 'exit'.\n"))
    while True:
        try:
            task = input(_cyan("shree› ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if task.lower() in {"exit", "quit", ":q"}:
            return 0
        if task:
            _run_task(task, workdir, autonomy, plan_only=False)
            print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="shree",
                                description="Shree — your AI coding agent")
    p.add_argument("task", nargs="*", help="the coding task (omit for REPL)")
    p.add_argument("-C", "--dir", default=os.getcwd(), help="repo directory")
    p.add_argument("--plan", action="store_true", help="plan only, no changes")
    p.add_argument("--auto", action="store_true",
                   help="auto-apply low-risk edits (approve risky/bash)")
    p.add_argument("--yolo", action="store_true", help="execute without asking")
    args = p.parse_args(argv)

    autonomy = ("yolo" if args.yolo else "auto_low_risk" if args.auto
                else "plan_first")
    workdir = os.path.abspath(args.dir)
    if not os.path.isdir(workdir):
        print(_red(f"not a directory: {workdir}"))
        return 2
    task = " ".join(args.task).strip()
    if not task:
        return _repl(workdir, autonomy)
    return _run_task(task, workdir, autonomy, plan_only=args.plan)


if __name__ == "__main__":
    raise SystemExit(main())
