# File: backend/app/routers/pnl.py
from __future__ import annotations
import os
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, confloat
from dotenv import load_dotenv
from app.services.pnl_source import get_day_pnl, set_day_pnl

load_dotenv(override=True)

router = APIRouter(prefix="/pnl", tags=["pnl"])

class PnLUpdate(BaseModel):
    day_pnl: confloat(ge=-1e9, le=1e9)

@router.get("/current")
def pnl_current() -> Dict[str, Any]:
    log_dir = os.getenv("LOG_DIR", r"C:\AI files\Orion\orion-backend\logs")
    pnl = get_day_pnl(log_dir)
    return {"ok": True, "day_pnl": pnl}

@router.post("/set")
def pnl_set(payload: PnLUpdate) -> Dict[str, Any]:
    """
    DEV/TEST ONLY: Persist current day PnL in LOG_DIR/pnl.json.
    """
    log_dir = os.getenv("LOG_DIR", r"C:\AI files\Orion\orion-backend\logs")
    path = set_day_pnl(log_dir, float(payload.day_pnl))
    return {"ok": True, "path": path, "day_pnl": payload.day_pnl}
