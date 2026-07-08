"""CLI: run the golden regression suite against the LIVE reply pipeline.

    .venv/bin/python -m app.scripts.run_golden            # all cases
    .venv/bin/python -m app.scripts.run_golden social-brevity identity-pin

Uses real providers (network + tokens): run on demand and before deploying any
behavioral (prompt/directive) change. Exit code 0 = all passed.
"""
from __future__ import annotations

import sys

from app.brain import golden


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or None
    summary = golden.run_all(names)
    for r in summary["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['name']}")
        for c in r["checks"]:
            status = {True: "ok", False: "FAIL", None: "skip"}[c["passed"]]
            observed = f"  ({c['observed']})" if c.get("observed") is not None else ""
            print(f"    {status:4s} {c['check']}{observed}")
        if not r["passed"]:
            print(f"    reply: {r['reply'][:200]!r}")
    print(f"\n{summary['passed']}/{summary['total']} passed")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
