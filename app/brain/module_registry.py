"""Transactional registry controlled by the Parent Kernel."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select

from app.brain.capability_registry import validate_capabilities
from app.db.models import (
    ModuleCapabilityEnvelope, ModuleControlLog, SelfModule, session_scope,
)

MODULE_TYPES = {"emotion", "memory", "reasoning", "speech", "tool", "agent",
                "evaluator", "safety_helper", "business", "erp", "tody",
                "curriculum", "self_model", "other"}
STATUSES = {"inactive", "shadow", "canary_5", "canary_25", "active", "failed",
            "rollback", "disabled"}
_KEY = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], sort_keys=True)


def _policy_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_module_identity(module_key: str, module_type: str, status: str = "inactive") -> None:
    if not _KEY.fullmatch(module_key) or len(module_key) > 120:
        raise ValueError("module_key must be lowercase snake_case, max 120 characters")
    if module_type not in MODULE_TYPES:
        raise ValueError(f"unsupported module_type: {module_type}")
    if status not in STATUSES:
        raise ValueError(f"unsupported module status: {status}")
    if module_key in {"parent_brain", "core_kernel", "safety_policy", "approval_gate"}:
        raise ValueError("authority modules cannot be child modules")


def register_module(proposal: dict, *, created_by: str = "system") -> dict:
    key, kind = proposal["module_key"].lower(), proposal["module_type"]
    validate_module_identity(key, kind)
    risk = proposal.get("risk_level", "low")
    allowed = proposal.get("allowed_actions", [])
    blocked = proposal.get("blocked_actions", [])
    capabilities = validate_capabilities(key, allowed, blocked, risk,
                                          filesystem_scope=proposal.get("filesystem_scope", []),
                                          network_scope=proposal.get("network_scope", []),
                                          data_scope=proposal.get("data_scope", []))
    if not capabilities["valid"]:
        raise ValueError("invalid capabilities: " + "; ".join(capabilities["issues"]))
    if risk in {"medium", "high", "critical"} and not proposal.get("fallback_module_key"):
        raise ValueError("medium/high/critical modules require a fallback_module_key")
    with session_scope() as db:
        if db.scalar(select(SelfModule).where(SelfModule.module_key == key)):
            raise ValueError("module_key already registered")
        module = SelfModule(module_key=key, module_name=proposal["module_name"],
                            module_type=kind, version=proposal.get("version", "0.1.0"),
                            sandbox_path=proposal.get("sandbox_path", "app/sandbox"),
                            allowed_actions_json=_json(capabilities["allowed_actions"]),
                            blocked_actions_json=_json(capabilities["blocked_actions"]),
                            fallback_module_key=proposal.get("fallback_module_key"),
                            created_by=created_by)
        db.add(module)
        db.flush()
        snapshot = {"module_key": key, "version": module.version,
                    "allowed_actions": capabilities["allowed_actions"],
                    "blocked_actions": capabilities["blocked_actions"], "risk_level": risk}
        db.add(ModuleCapabilityEnvelope(module_key=key, version=module.version,
            risk_level=risk, allowed_actions_json=_json(capabilities["allowed_actions"]),
            blocked_actions_json=_json(capabilities["blocked_actions"]),
            requires_approval=capabilities["requires_approval"],
            filesystem_scope_json=_json(proposal.get("filesystem_scope", [])),
            network_scope_json=_json(proposal.get("network_scope", [])),
            data_scope_json=_json(proposal.get("data_scope", [])),
            policy_hash=_policy_hash(snapshot), policy_snapshot_hash=_policy_hash(snapshot),
            created_by=created_by))
        db.add(ModuleControlLog(module_key=key, version=module.version, action="register",
                                old_status=None, new_status="inactive", reason="registered",
                                approved_by=created_by))
        return {"module_key": key, "version": module.version, "status": module.status,
                "requires_approval": capabilities["requires_approval"]}


def get_module(module_key: str) -> dict | None:
    with session_scope() as db:
        item = db.scalar(select(SelfModule).where(SelfModule.module_key == module_key))
        if not item:
            return None
        return {c.name: getattr(item, c.name) for c in SelfModule.__table__.columns}


def list_modules(status: str | None = None, module_type: str | None = None) -> list[dict]:
    with session_scope() as db:
        stmt = select(SelfModule).order_by(SelfModule.module_key)
        if status: stmt = stmt.where(SelfModule.status == status)
        if module_type: stmt = stmt.where(SelfModule.module_type == module_type)
        return [{c.name: getattr(x, c.name) for c in SelfModule.__table__.columns} for x in db.scalars(stmt)]


def update_module_status(module_key: str, status: str, reason: str, *, approved_by: str | None = None) -> dict:
    if status not in STATUSES: raise ValueError(f"unsupported module status: {status}")
    with session_scope() as db:
        item = db.scalar(select(SelfModule).where(SelfModule.module_key == module_key))
        if not item: raise ValueError("module not found")
        old = item.status; item.status = status
        db.add(ModuleControlLog(module_key=module_key, version=item.active_version or item.version,
                                 action="status_change", old_status=old, new_status=status,
                                 reason=reason, approved_by=approved_by))
        return {"module_key": module_key, "old_status": old, "new_status": status}


def get_active_version(module_key: str) -> str | None:
    item = get_module(module_key)
    return item.get("active_version") if item else None


def set_active_version(module_key: str, version: str, approved_by: str) -> dict:
    if not approved_by: raise ValueError("approved_by is required")
    with session_scope() as db:
        item = db.scalar(select(SelfModule).where(SelfModule.module_key == module_key))
        if not item: raise ValueError("module not found")
        old = item.active_version; item.active_version = version; item.status = "active"
        db.add(ModuleControlLog(module_key=module_key, version=version, action="activate",
                                old_status="active" if old else "inactive", new_status="active",
                                reason="approved activation", approved_by=approved_by))
        return {"module_key": module_key, "active_version": version, "approved_by": approved_by}


def get_fallback(module_key: str) -> str | None:
    item = get_module(module_key)
    return item.get("fallback_module_key") if item else None


def log_module_event(module_key: str, action: str, old_status: str | None,
                     new_status: str, reason: str, metadata: dict | None = None) -> None:
    with session_scope() as db:
        db.add(ModuleControlLog(module_key=module_key, action=action, old_status=old_status,
                                new_status=new_status, reason=reason,
                                metadata_json=json.dumps(metadata or {}, sort_keys=True)))
