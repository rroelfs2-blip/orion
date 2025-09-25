# File: backend/app/routers/alpaca.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)

# IMPORTANT: standardized prefix (no '/api' here)
router = APIRouter(prefix="/alpaca", tags=["alpaca"])

# --- Optional client wiring (safe fallback if not present) -------------------
def _maybe_client():
    """
    Try to import an internal Alpaca client if you have one wired.
    Otherwise return None and serve static-safe responses.
    """
    for mod in ("app.services.alpaca_client", "app.integrations.alpaca_client", "app.adapters.alpaca"):
        try:
            return __import__(mod, fromlist=["AlpacaClient"]).AlpacaClient  # type: ignore[attr-defined]
        except Exception:
            continue
    return None

# Simple models (expand later if you wire a real client)
class ValidateAssetsRequest(BaseModel):
    symbols: list[str]

@router.get("/clock")
def get_clock() -> Dict[str, Any]:
    Client = _maybe_client()
    if Client:
        return Client().get_clock()  # type: ignore[call-arg]
    # Safe fallback
    return {"ok": True, "source": "fallback", "clock": {"is_open": False}}

@router.get("/account")
def get_account() -> Dict[str, Any]:
    Client = _maybe_client()
    if Client:
        return Client().get_account()  # type: ignore[call-arg]
    return {"ok": True, "source": "fallback", "account": {"status": "paper", "equity": None}}

@router.get("/debug")
def alpaca_debug() -> Dict[str, Any]:
    return {
        "ok": True,
        "env": {
            "ALPACA_BASE_URL": os.getenv("ALPACA_BASE_URL", "<unset>"),
            "ALPACA_KEY_ID": "***" if os.getenv("ALPACA_KEY_ID") else None,
            "ALPACA_SECRET": "***" if os.getenv("ALPACA_SECRET") else None,
            "MODE": os.getenv("APP_NAME", "orion-backend"),
        },
    }

@router.get("/asset/{symbol}")
def get_asset(symbol: str) -> Dict[str, Any]:
    Client = _maybe_client()
    if Client:
        return Client().get_asset(symbol)  # type: ignore[call-arg]
    if not symbol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="symbol required")
    return {"ok": True, "source": "fallback", "symbol": symbol.upper(), "tradable": True}

@router.post("/assets/validate")
def validate_assets(req: ValidateAssetsRequest) -> Dict[str, Any]:
    Client = _maybe_client()
    if Client:
        return Client().validate_assets(req.symbols)  # type: ignore[call-arg]
    return {"ok": True, "source": "fallback", "valid": [s.upper() for s in req.symbols]}
