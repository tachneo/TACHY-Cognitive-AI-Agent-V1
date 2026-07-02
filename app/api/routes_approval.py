"""Approval routes — request, respond, and list pending high-risk actions."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.safety import approvals

router = APIRouter(prefix="/approval", tags=["approval"])


class ApprovalRequest(BaseModel):
    action: str = Field(min_length=1, max_length=255)
    payload: str | None = Field(default=None, max_length=20000)


class ApprovalResponse(BaseModel):
    approval_id: int = Field(gt=0)
    approved: bool


@router.post("/request")
def request_approval(req: ApprovalRequest) -> dict:
    return approvals.request_approval(req.action, req.payload)


@router.post("/respond")
def respond(req: ApprovalResponse) -> dict:
    return approvals.respond(req.approval_id, req.approved)


@router.get("/pending")
def pending(limit: int = Query(default=50, ge=1, le=100)) -> dict:
    rows = approvals.list_pending(limit=limit)
    return {"count": len(rows), "pending": rows}
