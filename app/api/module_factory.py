from fastapi import APIRouter, HTTPException
from app.brain import module_registry, self_model, self_module_factory

router = APIRouter(prefix="/brain", tags=["self-improvement"])

@router.get("/modules")
def modules(status: str | None = None, module_type: str | None = None): return {"ok": True, "data": module_registry.list_modules(status, module_type), "error": None}
@router.get("/modules/{module_key}")
def module(module_key: str):
    data = module_registry.get_module(module_key)
    if not data: raise HTTPException(404, "module not found")
    return {"ok": True, "data": data, "error": None}
@router.post("/modules/propose")
def propose(): return {"ok": True, "data": self_module_factory.detect_and_propose(), "error": None}
@router.get("/self-model")
def state(): return {"ok": True, "data": self_model.get_self_state(), "error": None}
@router.post("/self-model/update")
def update(payload: dict): return {"ok": True, "data": self_model.update_self_state(payload.get("event", ""), payload.get("evidence", ""), payload.get("confidence", 0), payload.get("metadata")), "error": None}
@router.post("/self-model/reflect")
def reflect(payload: dict): return {"ok": True, "data": self_model.identity_reflection(payload.get("question", ""), payload.get("context")), "error": None}
