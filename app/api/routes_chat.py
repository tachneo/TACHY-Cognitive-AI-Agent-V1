"""Chat route — entry point into the cognitive loop."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain.attention_system import Signals
from app.brain.cognitive_loop import process

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    security_risk: int = Field(default=0, ge=0, le=10)
    money_impact: int = Field(default=0, ge=0, le=10)
    client_impact: int = Field(default=0, ge=0, le=10)
    urgency: int = Field(default=0, ge=0, le=10)
    guardian_interest: int = Field(default=0, ge=0, le=10)
    emotional_weight: int = Field(default=0, ge=0, le=10)


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
