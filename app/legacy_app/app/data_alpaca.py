# File: app/legacy_app/app/data_alpaca.py
from __future__ import annotations
import os, time, random, datetime as dt
from typing import List, Dict, Any, Optional
import requests

ALP_BASE = "https://data.alpaca.markets/v2/stocks"

def _alpaca_keys() -> Optional[Dict[str, str]]:
    kid = os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_KEY") or os.getenv("APCA_API_KEY_ID")
    sec = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_SECRET") or os.getenv("APCA_API_SECRET_KEY")
    if kid and sec:
        return {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}
    return None

def get_bars_alpaca(symbol: str, timeframe: str = "1Min", limit: int = 50) -> List[Dict[str, Any]]:
    keys = _alpaca_keys()
    if not keys:
        raise RuntimeError("alpaca_keys_missing")
    url = f"{ALP_BASE}/{symbol}/bars"
    params = {"timeframe": timeframe, "limit": max(1, min(int(limit or 50), 1000))}
    r = requests.get(url, params=params, headers=keys, timeout=20)
    r.raise_for_status()
    js = r.json()
    bars = js.get("bars") or []
    out: List[Dict[str, Any]] = []
    for b in bars:
        out.append({"t": b.get("t"), "o": b.get("o"), "h": b.get("h"),
                    "l": b.get("l"), "c": b.get("c"), "v": b.get("v")})
    return out

def generate_synthetic_bars(n: int = 50, start: float = 430.0) -> List[Dict[str, Any]]:
    random.seed(42)
    out: List[Dict[str, Any]] = []
    px = float(start)
    now = int(time.time())
    for i in range(max(1, n)):
        drift = (random.random() - 0.5) * 2.0
        o = px
        c = max(0.01, o + drift)
        h = max(o, c) + random.random() * 0.8
        l = min(o, c) - random.random() * 0.8
        px = c
        t = dt.datetime.utcfromtimestamp(now - 60 * (n - i)).isoformat() + "Z"
        out.append({"t": t, "o": round(o, 4), "h": round(h, 4), "l": round(l, 4), "c": round(c, 4)})
    return out
