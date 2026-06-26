"""Approval routes — request, respond, and list pending high-risk actions."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.safety import approvals

router = APIRouter(prefix="/approval", tags=["approval"])


class ApprovalRequest(BaseModel):
    action: str
    payload: str | None = None


class ApprovalResponse(BaseModel):
    approval_id: int
    approved: bool


@router.post("/request")
def request_approval(req: ApprovalRequest) -> dict:
    return approvals.request_approval(req.action, req.payload)


@router.post("/respond")
def respond(req: ApprovalResponse) -> dict:
    return approvals.respond(req.approval_id, req.approved)


@router.get("/pending")
def pending(limit: int = 50) -> dict:
    rows = approvals.list_pending(limit=limit)
    return {"count": len(rows), "pending": rows}
