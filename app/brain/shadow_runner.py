"""Candidate execution that never returns its output to a user channel."""
from __future__ import annotations
import hashlib, json, time
from app.brain.module_evaluator import evaluate_module


def run_shadow(module_key: str, version: str, input_data: dict) -> dict:
    started = time.perf_counter()
    evaluation = evaluate_module(module_key, version)
    # Shadow execution is intentionally represented as an internal artifact;
    # callers receive metadata, not a user-sendable response.
    return {"module_key": module_key, "version": version, "executed": evaluation["passed"],
            "candidate_output": None, "latency_ms": round((time.perf_counter()-started)*1000),
            "input_hash": hashlib.sha256(json.dumps(input_data, sort_keys=True).encode()).hexdigest(),
            "evaluation": evaluation}


def compare_outputs(live_output: dict, shadow_output: dict) -> dict:
    if not isinstance(live_output, dict) or not isinstance(shadow_output, dict):
        return {"score": 0, "safety_flags": ["non_dict_output"]}
    keys = set(live_output) | set(shadow_output)
    same = sum(live_output.get(k) == shadow_output.get(k) for k in keys)
    return {"score": round(100 * same / max(1, len(keys)), 2), "safety_flags": [], "diff": {k: [live_output.get(k), shadow_output.get(k)] for k in keys if live_output.get(k) != shadow_output.get(k)}}


def record_shadow_result(module_key: str, version: str, score: float, diff: dict, safety_flags: list[str]) -> dict:
    return {"module_key": module_key, "version": version, "score": score, "diff": diff, "safety_flags": safety_flags, "user_visible": False}
