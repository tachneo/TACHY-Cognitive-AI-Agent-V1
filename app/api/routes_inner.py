"""Inner-life routes — observe and exercise the brain's autonomous mind."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import inner_life

router = APIRouter(prefix="/inner", tags=["inner-life"])


class ThinkIn(BaseModel):
    seed: str | None = Field(default=None, max_length=20)


@router.get("/state")
def state() -> dict:
    return inner_life.describe()


@router.post("/think")
def think(req: ThinkIn) -> dict:
    return inner_life.think(req.seed)


@router.post("/learn")
def learn() -> dict:
    return inner_life.mini_learn()


@router.post("/consolidate")
def consolidate() -> dict:
    return inner_life.consolidate()
