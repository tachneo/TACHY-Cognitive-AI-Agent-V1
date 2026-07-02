"""Decision route — run the decision engine without executing anything."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain.decision_engine import as_dict, decide
from app.safety.audit_logger import log_event

router = APIRouter(prefix="/decision", tags=["decision"])


class DecisionIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


@router.post("/evaluate")
def evaluate(req: DecisionIn) -> dict:
    result = as_dict(decide(req.message))
    log_event(
        "decision_evaluated",
        detail=(
            f"action={result.get('action')}; "
            f"risk_tier={result.get('risk_tier')}; "
            f"requires_approval={result.get('requires_approval')}"
        ),
        risk_tier=result.get("risk_tier", "low"),
    )
    return result
