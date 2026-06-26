"""Reflection route — run the daily learning loop."""
from __future__ import annotations

from fastapi import APIRouter

from app.brain.learning_engine import daily_reflection

router = APIRouter(prefix="/reflection", tags=["reflection"])


@router.post("/daily")
def daily() -> dict:
    return daily_reflection()
