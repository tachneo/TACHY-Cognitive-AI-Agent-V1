"""Golden regression harness — Shree's mistake history as a permanent test
suite (metacognitive loop, the verification half of self-repair).

Code fixes are verified by pytest; BEHAVIORAL fixes had no harness — so a
directive patch for one failure could silently regress another (prompt rules
interact). This closes that gap: each case in tests/golden/cases.yaml replays a
real past failure through the LIVE reply pipeline and asserts the failure stays
fixed. The contract for every future self-repair: add the golden case FIRST,
then fix, then deploy only if the new case passes and no old case regresses.

Checks per case, cheapest first:
  1. deterministic — max_sentences and forbidden regexes (free, no LLM)
  2. judged — each criterion answered strictly YES/NO by the light pool model

Runs the REAL provider chain (network + tokens), so it is invoked on demand —
`python -m app.scripts.run_golden` — and before behavioral deploys; it is NOT
part of the hermetic pytest suite.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.brain.self_repo import SHREE_HOME

CASES_PATH = SHREE_HOME / "tests" / "golden" / "cases.yaml"

_SENTENCE_SPLIT = re.compile(r"[.!?।]+")
_JUDGE_SYSTEM = (
    "You are a strict test judge for a chat assistant's reply. You will be "
    "given the REPLY and one CRITERION. Decide whether the reply satisfies "
    "the criterion. Answer with ONLY the single word YES or NO."
)


def load_cases() -> list[dict]:
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8")) or []
    return [c for c in data if c.get("name") and c.get("message")]


def _sentence_count(text: str) -> int:
    return len([s for s in _SENTENCE_SPLIT.split(text or "") if s.strip()])


_judge_provider_cache = None


def _judge_provider():
    """A DETERMINISTIC judge: the pool's chat tiers run at temperature 1.0 (good
    for conversation, fatal for a test judge — verdicts flip between runs). The
    judge gets its own low-temperature instance of the light model."""
    global _judge_provider_cache
    if _judge_provider_cache is None:
        from app.config import get_settings
        from app.llm.provider import NvidiaChatProvider, get_light_provider
        s = get_settings()
        model = (s.light_nvidia_model or "").strip()
        key = (s.light_nvidia_key or "").strip()
        if s.llm_multi_enabled and model and key:
            _judge_provider_cache = NvidiaChatProvider(
                key, model, s.nvidia_base_url, temperature=0.1, top_p=0.9,
                max_tokens_cap=512,
                chat_template_kwargs=({"enable_thinking": True}
                                      if "gemma" in model else None),
                read_timeout=30)
        else:
            _judge_provider_cache = get_light_provider()
    return _judge_provider_cache


def _judge(reply: str, criterion: str) -> bool:
    prompt = f"REPLY:\n{reply[:1200]}\n\nCRITERION: {criterion}\n\nAnswer:"
    verdict = (_judge_provider().complete(_JUDGE_SYSTEM, prompt,
                                          max_tokens=400) or "").strip()
    # Robust parse: the model may preface the verdict — take the LAST yes/no.
    tokens = re.findall(r"\b(YES|NO)\b", verdict.upper())
    return bool(tokens) and tokens[-1] == "YES"


def generate_reply(case: dict) -> str:
    """One pass of the real reply pipeline for this case's persona + context."""
    from app.brain.cognitive_loop import process
    result = process(
        case["message"],
        context=(case.get("context") or ""),
        channel="chat",
        related_person=case.get("person"),
    )
    return result.get("reply", "")


def run_case(case: dict, *, reply: str | None = None) -> dict:
    """Run one golden case. Returns pass/fail with per-check detail."""
    reply = reply if reply is not None else generate_reply(case)
    checks: list[dict] = []
    # 1. deterministic (free)
    max_sentences = case.get("max_sentences")
    if max_sentences:
        n = _sentence_count(reply)
        checks.append({"check": f"max_sentences<={max_sentences}",
                       "passed": n <= int(max_sentences), "observed": n})
    for pattern in case.get("forbid") or []:
        hit = re.search(pattern, reply or "")
        checks.append({"check": f"forbid:{pattern}", "passed": hit is None,
                       "observed": hit.group(0)[:40] if hit else None})
    # 2. judged (light model) — skipped if a deterministic check already failed,
    # so a broken reply doesn't burn judge calls.
    if all(c["passed"] for c in checks):
        for criterion in case.get("criteria") or []:
            try:
                ok = _judge(reply, criterion)
            except Exception as exc:  # noqa: BLE001 — judge outage ≠ regression
                checks.append({"check": f"judge:{criterion[:50]}",
                               "passed": None,
                               "observed": f"judge error {type(exc).__name__}"})
                continue
            checks.append({"check": f"judge:{criterion[:50]}", "passed": ok,
                           "observed": None})
    hard_fail = any(c["passed"] is False for c in checks)
    return {"name": case["name"], "passed": not hard_fail,
            "reply": (reply or "")[:400], "checks": checks}


def run_all(names: list[str] | None = None) -> dict:
    """Run every case (or a named subset). The deploy gate for behavioral
    fixes: all_passed must be True before a directive/prompt change ships."""
    results = []
    for case in load_cases():
        if names and case["name"] not in names:
            continue
        results.append(run_case(case))
    return {"total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "all_passed": all(r["passed"] for r in results) if results else False,
            "results": results}
