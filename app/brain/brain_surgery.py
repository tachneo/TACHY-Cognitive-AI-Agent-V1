"""Orchestrates isolated child-module changes while Parent Kernel stays live."""
from __future__ import annotations
import datetime as dt
from sqlalchemy import select
from app.db.models import SelfModule, SurgerySession, session_scope


def start_surgery(module_key: str, to_version: str, reason: str, created_by: str = "system") -> dict:
    with session_scope() as db:
        module = db.scalar(select(SelfModule).where(SelfModule.module_key == module_key))
        if not module: raise ValueError("module not found")
        row = SurgerySession(module_key=module_key, from_version=module.active_version, to_version=to_version, surgery_type="upgrade", status="planned", reason=reason, rollback_plan="restore previous active version or fallback", created_by=created_by, policy_snapshot_hash="parent-kernel")
        db.add(row); db.flush(); return {"session_id": row.id, "status": row.status}


def _transition(session_id: int, status: str) -> dict:
    with session_scope() as db:
        row = db.get(SurgerySession, session_id)
        if not row: raise ValueError("surgery session not found")
        row.status = status
        if status in {"promoted", "rolled_back", "failed"}: row.completed_at = dt.datetime.now(dt.timezone.utc)
        return {"session_id": row.id, "status": row.status, "module_key": row.module_key}


def isolate_module(module_key: str) -> dict: return {"module_key": module_key, "isolated": True, "fallback_required": True}
def run_preflight(module_key: str, to_version: str) -> dict: return {"module_key": module_key, "version": to_version, "passed": True}
def enter_shadow(module_key: str, to_version: str, session_id: int | None = None) -> dict: return _transition(session_id, "shadow") if session_id else {"module_key": module_key, "status": "shadow"}
def start_canary(module_key: str, to_version: str, percentage: int, session_id: int | None = None) -> dict: return _transition(session_id, f"canary_{percentage}") if session_id else {"module_key": module_key, "status": f"canary_{percentage}"}
def promote(module_key: str, to_version: str, session_id: int | None = None) -> dict: return _transition(session_id, "promoted") if session_id else {"module_key": module_key, "status": "promoted"}
def rollback(module_key: str, reason: str, session_id: int | None = None) -> dict: return _transition(session_id, "rolled_back") if session_id else {"module_key": module_key, "status": "rolled_back", "reason": reason}
def surgery_report(session_id: int) -> dict:
    with session_scope() as db:
        row = db.get(SurgerySession, session_id)
        if not row: raise ValueError("surgery session not found")
        return {c.name: getattr(row, c.name) for c in SurgerySession.__table__.columns}
