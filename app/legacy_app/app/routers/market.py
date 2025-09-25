# File: app/legacy_app/app/routers/market.py
from __future__ import annotations
import asyncio, json, os, time, random
from typing import List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from ..data_alpaca import get_bars_alpaca, generate_synthetic_bars

router = APIRouter()

@router.get("/data/history")
def history(
    symbol: str = Query(..., min_length=1, description="Ticker, e.g., SPY"),
    timeframe: str = Query("1Min"),
    limit: int = Query(50, ge=1, le=1000),
):
    try:
        return get_bars_alpaca(symbol.strip().upper(), timeframe=timeframe, limit=limit)
    except Exception:
        return generate_synthetic_bars(n=limit, start=430.0)

@router.websocket("/ws/price")
async def ws_price(ws: WebSocket, symbol: str):
    await ws.accept()
    sym = (symbol or "SPY").upper()
    try:
        px = 430.0 + random.random()
        while True:
            drift = (random.random() - 0.5) * 0.4
            px = max(0.01, px + drift)
            await ws.send_text(json.dumps({"symbol": sym, "t": int(time.time()*1000), "price": round(px, 4)}))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
