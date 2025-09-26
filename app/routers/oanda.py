# File: app/routers/oanda.py
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.oanda_client import OandaClient, load_oanda_config

router = APIRouter(prefix="/oanda", tags=["oanda"])

# Paper-only by default; we only expose GET-style, read-safe endpoints here.


class PricesQuery(BaseModel):
    instruments: List[str] = Field(default_factory=list)
    account_id: Optional[str] = None


@router.get("/status")
def oanda_status():
    client = OandaClient()
    return client.status()


@router.get("/time")
def oanda_time():
    client = OandaClient()
    return client.server_time()


@router.get("/accounts")
def oanda_accounts():
    client = OandaClient()
    return client.accounts()


@router.get("/instruments")
def oanda_instruments(account_id: Optional[str] = Query(default=None)):
    client = OandaClient()
    return client.instruments(account_id=account_id)


@router.get("/prices")
def oanda_prices(instruments: str = Query(default=""), account_id: Optional[str] = Query(default=None)):
    # instruments: comma-separated symbol list (e.g., "EUR_USD,USD_JPY")
    symbols = [s.strip() for s in instruments.split(",") if s.strip()] if instruments else []
    client = OandaClient()
    return client.prices(instruments=symbols, account_id=account_id)


# Streaming placeholders — not active yet (kept safe)
@router.post("/stream/start")
def stream_start():
    cfg = load_oanda_config()
    return {
        "ok": False,
        "implemented": False,
        "mode": "paper" if cfg.practice else "live",
        "message": "Price stream not implemented in skeleton. This endpoint is a placeholder.",
    }


@router.post("/stream/stop")
def stream_stop():
    return {"ok": True, "message": "No active stream in skeleton."}
