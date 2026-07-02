"""Agent route — run a skill agent (auto-routed or explicit)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.agents.main_agent import handle, route
from app.safety.audit_logger import log_event

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    agent: str | None = Field(default=None, pattern="^(security|coding|business)$")
    project: str | None = Field(default=None, max_length=64)


@router.post("/run")
def run(req: AgentRequest) -> dict:
    result = handle(req.message, agent=req.agent, project=req.project)
    log_event(
        "agent_run",
        detail=f"agent={result.agent}; project={req.project or 'GENERAL'}",
        risk_tier="medium",
    )
    return asdict(result)


@router.get("/route")
def which(message: str = Query(min_length=1, max_length=8000)) -> dict:
    agent = route(message)
    log_event("agent_routed", detail=f"agent={agent}", risk_tier="low")
    return {"message": message, "agent": agent}
