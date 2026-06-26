"""Chat route — entry point into the cognitive loop."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.brain.attention_system import Signals
from app.brain.cognitive_loop import process

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    security_risk: int = 0
    money_impact: int = 0
    client_impact: int = 0
    urgency: int = 0
    guardian_interest: int = 0
    emotional_weight: int = 0


@router.post("/chat")
def chat(req: ChatRequest) -> dict:
    signals = Signals(
        security_risk=req.security_risk,
        money_impact=req.money_impact,
        client_impact=req.client_impact,
        urgency=req.urgency,
        guardian_interest=req.guardian_interest,
        emotional_weight=req.emotional_weight,
    )
    return process(req.message, signals)
