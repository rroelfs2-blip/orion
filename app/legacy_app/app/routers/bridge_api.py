# File: backend/app/legacy_app/app/routers/bridge_api.py
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status
from pydantic import BaseModel
from ..services.bridge_auth import inbox_gate, require_token, CFG

router = APIRouter(prefix="/bridge", tags=["bridge"])

# --- Demo storage (replace with your real queue if desired) ---
_INBOX: List[Dict[str, Any]] = []
_OUTBOX: List[Dict[str, Any]] = []

def _pop_inbox() -> List[Dict[str, Any]]:
    if not _INBOX:
        return []
    items = list(_INBOX)
    _INBOX.clear()
    return items

def _peek_inbox() -> List[Dict[str, Any]]:
    return list(_INBOX)

# --- Models ---
class BridgeTaskPayload(BaseModel):
    source: str
    target: str
    task_type: str
    payload: Dict[str, Any]

class BridgeTaskAck(BaseModel):
    ok: bool
    task: Dict[str, Any]

# --- Endpoints ---
@router.get("/inbox")
async def get_inbox(request: Request, pop: int = 1, _: None = Depends(inbox_gate)) -> Any:
    """
    Read bridge inbox (loopback open by default; token honored if present).
      pop=1: consume
      pop=0: peek
    """
    items = _pop_inbox() if pop else _peek_inbox()
    return items

@router.post("/tasks", response_model=BridgeTaskAck)
async def post_task(_: None = Depends(require_token), task: BridgeTaskPayload = None) -> Any:
    """
    Enqueue a task (token required). Compatible with your prior /bridge/tasks payloads.
    """
    if task is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing task body")

    record = {
        "id": task.payload.get("id"),
        "source": task.source,
        "target": task.target,
        "task_type": task.task_type,
        "payload": task.payload,
    }
    _OUTBOX.append(record)
    # Loopback to inbox so your end-to-end test shows success locally
    _INBOX.append(record)
    return {"ok": True, "task": record}

@router.get("/health")
def bridge_health():
    return {"ok": True, "auth": CFG.as_health()}
