"""Decision route — run the decision engine without executing anything."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.brain.decision_engine import as_dict, decide

router = APIRouter(prefix="/decision", tags=["decision"])


class DecisionIn(BaseModel):
    message: str


@router.post("/evaluate")
def evaluate(req: DecisionIn) -> dict:
    return as_dict(decide(req.message))
