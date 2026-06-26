"""TODY routes — the brain's connection to the TODY app.

Reads are open; outbound actions are approval-gated (Phase-1D safety):
  POST /tody/send   -> queues an approval (does not send)
  POST /tody/send/execute -> sends only if that approval is approved
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents import tody_agent

router = APIRouter(prefix="/tody", tags=["tody"])


@router.get("/connect")
def connect() -> dict:
    return tody_agent.connect()


@router.get("/me")
def me() -> dict:
    return tody_agent.status()


@router.get("/conversations")
def conversations(limit: int = 20) -> dict:
    return tody_agent.inbox(limit=limit)


class SendIn(BaseModel):
    conversation_id: int
    body: str


@router.post("/send")
def send(req: SendIn) -> dict:
    """Queue an outbound message for approval (does not send)."""
    return tody_agent.request_send(req.conversation_id, req.body)


class SendExecuteIn(BaseModel):
    approval_id: int
    conversation_id: int
    body: str


@router.post("/send/execute")
def send_execute(req: SendExecuteIn) -> dict:
    """Send only if the referenced approval has been approved."""
    return tody_agent.execute_send(req.approval_id, req.conversation_id, req.body)


class PostIn(BaseModel):
    body: str


@router.post("/post")
def post(req: PostIn) -> dict:
    """Queue a post for approval (does not publish)."""
    return tody_agent.request_post(req.body)
