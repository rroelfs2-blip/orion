# File: backend/app/legacy_app/app/routers/bridge.py
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status
from pydantic import BaseModel
from ..services.auth import inbox_gate, require_token

router = APIRouter(prefix="/bridge", tags=["bridge"])

# --- Models (minimal; keep backward compatible with your prior payloads) ---

class BridgeTaskPayload(BaseModel):
    source: str
    target: str
    task_type: str
    payload: Dict[str, Any]

class BridgeTaskAck(BaseModel):
    ok: bool
    task: Dict[str, Any]

# --- Storage stubs / integration points ---
# NOTE: integrate these with your existing queue mechanisms if different.

_INBOX: List[Dict[str, Any]] = []   # temp fallback if your existing storage isn’t imported here
_OUTBOX: List[Dict[str, Any]] = []

def _pop_inbox_all() -> List[Dict[str, Any]]:
    if not _INBOX:
        return []
    items = list(_INBOX)
    _INBOX.clear()
    return items

def _peek_inbox() -> List[Dict[str, Any]]:
    return list(_INBOX)

# --- Endpoints ---

@router.get("/inbox")
async def get_inbox(request: Request, pop: int = 1, _: None = Depends(inbox_gate)) -> Any:
    """
    Read bridge inbox. Auth by inbox_gate (loopback_open defaults).
    - pop=1: consume and return messages
    - pop=0: return but do not consume
    """
    # If your project had a real store, swap these helpers for it.
    items = _pop_inbox_all() if pop else _peek_inbox()
    if not items:
        return []
    return items

@router.post("/tasks", response_model=BridgeTaskAck)
async def post_task(_: None = Depends(require_token), task: BridgeTaskPayload = None) -> Any:
    """
    Enqueue a task (token required). Mirrors your prior /bridge/tasks contract.
    """
    if task is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing task body")

    # In a real integration, push to your queue / handoff to Orion bridge
    record = {
        "id": task.payload.get("id") or None,
        "source": task.source,
        "target": task.target,
        "task_type": task.task_type,
        "payload": task.payload,
    }
    _OUTBOX.append(record)
    _INBOX.append(record)  # demo loopback to make E2E test pass locally

    return {"ok": True, "task": record}
