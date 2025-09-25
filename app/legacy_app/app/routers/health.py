# File: backend/app/legacy_app/app/routers/health.py
from fastapi import APIRouter
import os
from ..services.auth import CFG

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    return {
        "ok": True,
        "bridge_base": os.getenv("BRIDGE_BASE", "http://127.0.0.1:8001"),
        "poll_interval": 3,
        "auth": CFG.health_info(),
    }
