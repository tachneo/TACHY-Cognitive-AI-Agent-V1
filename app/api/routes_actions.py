"""Action routes — controlled automation (Phase 1E)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import action_engine

router = APIRouter(prefix="/actions", tags=["actions"])


class ProposeIn(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    params: dict = Field(default_factory=dict)


@router.get("/registry")
def registry() -> dict:
    return {"actions": action_engine.registry()}


@router.post("/propose")
def propose(req: ProposeIn) -> dict:
    return action_engine.propose(req.action, req.params)


@router.post("/execute/{approval_id}")
def execute(approval_id: int) -> dict:
    return action_engine.execute_approved(approval_id)
