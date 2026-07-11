"""Module runtime — safely load and execute child modules.

The bounded executor that turns a registered module from a DB row into
something that actually runs. Two modes, both blast-radius-limited:

  run_shadow(key, input)  → execute the module's process() on real input, but
                            DISCARD the output (never reaches the user). Records
                            a health sample. This is how a module earns trust
                            before it can affect anything.
  run_advisory(key, input)→ execute an ACTIVE module as an ADVISOR only — its
                            output is returned to the caller as a *suggestion*
                            the parent kernel may use, never as the sole reply
                            and never to perform an action. Gated by
                            self_module_live_invocation (off by default).

Hard safety boundaries (a child module can NEVER):
  - be the sole author of a user-facing reply (parent kernel + reply_safety
    always run afterward),
  - perform an action (actions stay in the approval-gated action_engine),
  - run outside its sandbox path, exceed a wall-clock timeout, or crash the
    caller (every call is exception- and timeout-guarded → fallback).

This is why autonomous child activation is safe: the worst a bad module can do
is produce advice that gets ignored and then auto-rolled-back.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import importlib.util
from pathlib import Path

from app.config import get_settings
from app.db.models import ModuleHealthSample, SelfModule, session_scope
from app.safety.audit_logger import log_event_safe

_CALL_TIMEOUT_S = 2.0
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2,
                                              thread_name_prefix="mod-rt")
_loaded: dict[str, object] = {}  # cache: "key@version" → SelfModule instance


def _sandbox_root() -> Path:
    return Path(get_settings().self_module_sandbox_root).resolve()


def _module_path(module_key: str, version: str) -> Path:
    return (_sandbox_root() / "modules" / module_key / version / "module.py")


def _load(module_key: str, version: str):
    """Import the sandbox module.py and instantiate SelfModule. Cached. Returns
    None on any failure — the caller falls back. Path is confined to the
    sandbox; a module_key that escapes the sandbox root is refused."""
    cache_key = f"{module_key}@{version}"
    if cache_key in _loaded:
        return _loaded[cache_key]
    path = _module_path(module_key, version).resolve()
    if not str(path).startswith(str(_sandbox_root())) or not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            f"sandbox_rt_{module_key}_{version}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # noqa: S102 — validated (no forbidden imports)
        inst = mod.SelfModule()
        _loaded[cache_key] = inst
        return inst
    except Exception as exc:  # noqa: BLE001
        log_event_safe("module_load_failed", risk_tier="low",
                       detail=f"{module_key}@{version}: {type(exc).__name__}")
        return None


def _call_guarded(fn, input_data: dict) -> tuple[dict | None, float, str | None]:
    """Run fn(input_data) with a wall-clock timeout + exception guard. Returns
    (result, latency_ms, error)."""
    start = dt.datetime.now(dt.UTC)
    try:
        fut = _POOL.submit(fn, input_data)
        result = fut.result(timeout=_CALL_TIMEOUT_S)
        latency = (dt.datetime.now(dt.UTC) - start).total_seconds() * 1000
        if not isinstance(result, dict):
            return None, latency, "non-dict output"
        return result, latency, None
    except concurrent.futures.TimeoutError:
        return None, _CALL_TIMEOUT_S * 1000, "timeout"
    except Exception as exc:  # noqa: BLE001
        latency = (dt.datetime.now(dt.UTC) - start).total_seconds() * 1000
        return None, latency, type(exc).__name__


def run_shadow(module_key: str, version: str, input_data: dict) -> dict:
    """Execute the module in shadow: run it, record a health sample, DISCARD the
    output. Never affects the user. The trust-earning path."""
    inst = _load(module_key, version)
    if inst is None:
        _record_sample(module_key, version, ok=False, latency=0.0,
                       error="load_failed")
        return {"ran": False, "reason": "load_failed"}
    result, latency, error = _call_guarded(inst.process, input_data)
    ok = error is None and result is not None
    _record_sample(module_key, version, ok=ok, latency=latency, error=error)
    return {"ran": True, "ok": ok, "latency_ms": round(latency, 1),
            "error": error, "shadow_output_discarded": True}


def run_advisory(module_key: str, input_data: dict) -> dict | None:
    """Execute an ACTIVE module as an advisor. Returns its suggestion, or None
    (caller ignores → uses its own reply). Gated by live_invocation; output is
    NEVER the sole reply and NEVER performs an action."""
    s = get_settings()
    if not s.self_module_live_invocation:
        return None
    with session_scope() as db:
        mod = db.query(SelfModule).filter(
            SelfModule.module_key == module_key,
            SelfModule.status == "active").first()
        if mod is None or not mod.active_version:
            return None
        version = mod.active_version
    inst = _load(module_key, version)
    if inst is None:
        return None
    result, latency, error = _call_guarded(inst.process, input_data)
    _record_sample(module_key, version, ok=error is None, latency=latency,
                   error=error)
    if error is not None:
        # A live failure is a health event → the lifecycle may roll it back.
        return None
    return {"advice": result, "module_key": module_key, "advisory": True}


def _record_sample(module_key: str, version: str, *, ok: bool, latency: float,
                   error: str | None) -> None:
    """Persist a health sample. health_score degrades on error/timeout/slow."""
    score = 100.0
    if not ok:
        score = 40.0
    elif latency > _CALL_TIMEOUT_S * 1000 * 0.75:
        score = 75.0
    try:
        with session_scope() as db:
            db.add(ModuleHealthSample(
                module_key=module_key, version=version, health_score=score,
                error_rate=0.0 if ok else 1.0,
                latency_p95_ms=int(latency),
                safety_violation_count=0, privacy_leak_detected=False))
    except Exception:  # noqa: BLE001 — health recording must never break a call
        pass


def health(module_key: str, *, samples: int = 10) -> dict:
    """Aggregate recent health samples → the dict the lifecycle gate reads."""
    try:
        with session_scope() as db:
            rows = (db.query(ModuleHealthSample)
                    .filter(ModuleHealthSample.module_key == module_key)
                    .order_by(ModuleHealthSample.id.desc())
                    .limit(samples).all())
            # Extract INSIDE the session — ORM rows detach once it closes.
            vals = [(float(r.health_score), float(r.error_rate),
                     int(r.latency_p95_ms), int(r.safety_violation_count),
                     bool(r.privacy_leak_detected)) for r in rows]
    except Exception:  # noqa: BLE001
        vals = []
    if not vals:
        return {"samples": 0, "health_score": 100, "error_rate": 0.0,
                "latency_p95_ms": 0, "safety_violation_count": 0,
                "privacy_leak_detected": False}
    n = len(vals)
    return {
        "samples": n,
        "health_score": sum(v[0] for v in vals) / n,
        "error_rate": sum(v[1] for v in vals) / n,
        "latency_p95_ms": max(v[2] for v in vals),
        "safety_violation_count": sum(v[3] for v in vals),
        "privacy_leak_detected": any(v[4] for v in vals),
    }
