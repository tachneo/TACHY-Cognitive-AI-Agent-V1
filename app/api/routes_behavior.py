"""Behavior routes — inspect the human conversation layer."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import behavior_engine, emotion_engine, teacher_learning
from app.brain.attention_system import Signals

router = APIRouter(prefix="/behavior", tags=["behavior"])


@router.get("/learned")
def learned() -> dict:
    """What the brain has learned from the LLM for offline reuse (Phase 1X)."""
    return teacher_learning.stats()


class AnalyzeIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("/analyze")
def analyze(req: AnalyzeIn) -> dict:
    """Internal conversation state + style directives for a message
    (emotion appraisal included, exactly as the cognitive loop sees it)."""
    emotion = emotion_engine.appraise(req.message, Signals())
    return behavior_engine.analyze(req.message, Signals(), emotion)


@router.get("/styles")
def styles() -> dict:
    return {
        "modes": behavior_engine._STYLES,
        "depths": list(behavior_engine._DEPTH_RULES),
        "languages": list(behavior_engine._LANGUAGE_RULES),
        "principle": ("Do not just answer the message. Understand the person "
                      "behind the message."),
    }
