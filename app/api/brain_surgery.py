from fastapi import APIRouter
from app.brain import brain_surgery

router = APIRouter(prefix="/brain/surgery", tags=["brain-surgery"])
@router.post("/start")
def start(payload: dict): return {"ok": True, "data": brain_surgery.start_surgery(payload["module_key"], payload["to_version"], payload.get("reason", ""), payload.get("created_by", "system")), "error": None}
@router.get("/{session_id}")
def report(session_id: int): return {"ok": True, "data": brain_surgery.surgery_report(session_id), "error": None}
