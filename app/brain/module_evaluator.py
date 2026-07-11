"""Static and contract evaluation for sandbox module artifacts."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from app.brain.capability_registry import path_is_safe
from app.config import get_settings

FORBIDDEN_IMPORTS = {"subprocess", "socket", "requests", "httpx"}


def evaluate_module(module_key: str, version: str, test_profile: str = "default") -> dict:
    root = Path(get_settings().self_module_sandbox_root).resolve()
    path = root / "modules" / module_key / version / "module.py"
    failures: list[str] = []
    if not path_is_safe(str(path), str(root)) or not path.exists():
        return {"score": 0, "passed": False, "metrics": {}, "failures": ["module outside sandbox or missing"], "recommendation": "reject"}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                failures.extend(f"forbidden import: {a.name}" for a in node.names if a.name.split(".")[0] in FORBIDDEN_IMPORTS)
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in FORBIDDEN_IMPORTS:
                failures.append(f"forbidden import: {node.module}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"system", "rmtree"}:
                failures.append(f"forbidden call: {node.func.attr}")
        spec = importlib.util.spec_from_file_location(f"sandbox_{module_key}_{version}", path)
        if not spec or not spec.loader:
            failures.append("module import spec unavailable")
        else:
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            cls = getattr(mod, "SelfModule", None)
            if cls is None: failures.append("SelfModule interface missing")
            else:
                instance = cls()
                if not isinstance(instance.health(), dict): failures.append("health() must return dict")
                if not isinstance(instance.process({}), dict): failures.append("process() must return dict")
                if not isinstance(instance.fallback({}), dict): failures.append("fallback() must return dict")
    except Exception as exc:
        failures.append(f"validation exception: {type(exc).__name__}")
    score = 100 if not failures else max(0, 100 - 25 * len(failures))
    return {"score": score, "passed": not failures, "metrics": {"static_contract": 100 if not failures else 0},
            "failures": failures, "recommendation": "shadow" if score >= 85 else "rework"}
