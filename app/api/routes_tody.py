"""TODY routes — the brain's connection to the TODY app.

Reads are open; outbound actions are approval-gated (Phase-1D safety):
  POST /tody/send   -> queues an approval (does not send)
  POST /tody/send/execute -> sends only if that approval is approved
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.agents import tody_agent
from app.agents import tody_activation
from app.agents import tody_worker

router = APIRouter(prefix="/tody", tags=["tody"])


@router.get("/connect")
def connect() -> dict:
    return tody_agent.connect()


@router.get("/me")
def me() -> dict:
    return tody_agent.status()


@router.get("/conversations")
def conversations(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return tody_agent.inbox(limit=limit)


@router.get("/messages")
def messages(conversation_id: int = Query(gt=0),
             limit: int = Query(default=30, ge=1, le=100)) -> dict:
    return tody_agent.messages(conversation_id=conversation_id, limit=limit)


class SendIn(BaseModel):
    conversation_id: int = Field(gt=0)
    body: str = Field(min_length=1, max_length=4000)
    reply_to_message_id: int | None = Field(default=None, gt=0)


@router.post("/send")
def send(req: SendIn) -> dict:
    """Queue an outbound message for approval (does not send)."""
    return tody_agent.request_send(req.conversation_id, req.body, req.reply_to_message_id)


class DraftReplyIn(BaseModel):
    conversation_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=4000)
    message_id: str | None = Field(default=None, max_length=100)
    sender_username: str | None = Field(default=None, max_length=100)
    sender_email: str | None = Field(default=None, max_length=255)
    sender_name: str | None = Field(default=None, max_length=255)


@router.post("/reply/draft")
def draft_reply(req: DraftReplyIn) -> dict:
    """Draft and queue a TODY reply for approval. Does not send."""
    return tody_agent.draft_reply_to_message(
        req.conversation_id,
        req.message,
        sender={
            "username": req.sender_username,
            "email": req.sender_email,
            "name": req.sender_name,
        },
        message_id=req.message_id,
    )


@router.post("/reply/guardian-direct")
def guardian_direct_reply(req: DraftReplyIn) -> dict:
    """Verified Rohit-only direct reply path."""
    return tody_agent.direct_reply_to_guardian(
        req.conversation_id,
        req.message,
        sender={
            "username": req.sender_username,
            "email": req.sender_email,
            "name": req.sender_name,
        },
        message_id=req.message_id,
    )


class ProcessLatestIn(BaseModel):
    conversation_id: int = Field(gt=0)
    limit: int = Field(default=10, ge=1, le=100)


@router.post("/reply/latest")
def reply_latest(req: ProcessLatestIn) -> dict:
    """Read latest message and queue a reply draft for approval. Does not send."""
    return tody_agent.process_latest_message(req.conversation_id, limit=req.limit)


@router.get("/reply/status")
def reply_status(limit: int = Query(default=50, ge=1, le=100)) -> dict:
    return tody_agent.reply_status(limit=limit)


@router.get("/conversation/status")
def conversation_status(conversation_id: int = Query(gt=0)) -> dict:
    return tody_agent.conversation_status(conversation_id)


@router.post("/growth-report/send")
def send_growth_report(conversation_id: int = Query(gt=0)) -> dict:
    return tody_agent.send_daily_growth_report(conversation_id)


@router.post("/curiosity/send")
def send_curiosity(conversation_id: int = Query(gt=0)) -> dict:
    return tody_agent.send_childlike_curiosity_message(conversation_id)


class WorkerPollIn(BaseModel):
    dry_run: bool = True
    conversation_limit: int = Field(default=10, ge=1, le=50)
    message_limit: int = Field(default=10, ge=1, le=50)


@router.get("/worker/status")
def worker_status() -> dict:
    return tody_worker.status()


@router.post("/worker/dry-run")
def worker_dry_run(req: WorkerPollIn) -> dict:
    return tody_worker.poll_once(
        dry_run=req.dry_run,
        conversation_limit=req.conversation_limit,
        message_limit=req.message_limit,
    )


@router.get("/activate/preflight")
def activation_preflight(check_login: bool = Query(default=False)) -> dict:
    return tody_activation.preflight(check_login=check_login)


@router.post("/activate/process-one")
def activation_process_one(req: WorkerPollIn) -> dict:
    return tody_activation.process_one(
        dry_run=req.dry_run,
        conversation_limit=req.conversation_limit,
        message_limit=req.message_limit,
    )


class SendExecuteIn(BaseModel):
    approval_id: int = Field(gt=0)
    conversation_id: int = Field(gt=0)
    body: str = Field(min_length=1, max_length=4000)
    reply_to_message_id: int | None = Field(default=None, gt=0)


@router.post("/send/execute")
def send_execute(req: SendExecuteIn) -> dict:
    """Send only if the referenced approval has been approved."""
    return tody_agent.execute_send(req.approval_id, req.conversation_id, req.body, req.reply_to_message_id)


class PostIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/post")
def post(req: PostIn) -> dict:
    """Queue a post for approval (does not publish)."""
    return tody_agent.request_post(req.body)


# ── Proactive initiative (Phase B + E) ───────────────────────────

@router.post("/proactive/cycle")
def proactive_cycle() -> dict:
    """Run one proactive observe→act cycle. Drafts an approval-gated message if
    there's something worth telling Papa (a closable curiosity question, an open
    promise, or a recent failure). Never auto-sends."""
    from app.agents import proactive
    return proactive.run_cycle()


@router.get("/proactive/queue")
def proactive_queue() -> dict:
    """Show the curiosity queue (unanswered questions Shree will close later)."""
    from app.agents import proactive
    return proactive._load_queue()
