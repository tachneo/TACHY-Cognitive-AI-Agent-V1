"""Agent route — run a skill agent (auto-routed or explicit)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.main_agent import handle, route

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str
    agent: str | None = None      # security | coding | business; None = auto-route
    project: str | None = None


@router.post("/run")
def run(req: AgentRequest) -> dict:
    result = handle(req.message, agent=req.agent, project=req.project)
    return asdict(result)


@router.get("/route")
def which(message: str) -> dict:
    return {"message": message, "agent": route(message)}
