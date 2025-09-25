# File: backend/app/pnl_service.py

from __future__ import annotations
import os, requests, time
from typing import Optional, Tuple

# Accept multiple env var names for compatibility
def _get_env(names):
    for n in names:
        v = os.getenv(n)
        if v:
            return v.strip().strip("'").strip('"')
    return None

ALPACA_KEY    = _get_env(["ALPACA_API_KEY_ID", "APCA_API_KEY_ID", "ALPACA_KEY"])
ALPACA_SECRET = _get_env(["ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY", "ALPACA_SECRET"])
ALPACA_ENV    = (os.getenv("ALPACA_ENV") or "paper").strip().lower()
BASE_DEFAULT  = "https://api.alpaca.markets/v2" if ALPACA_ENV == "live" else "https://paper-api.alpaca.markets/v2"
ALPACA_BASE   = (os.getenv("ALPACA_BASE_URL") or BASE_DEFAULT).rstrip("/")

# Simple in-process cache to avoid rate limits
_last_fetch_ts: float = 0.0
_last_equity: Optional[float] = None
_equity: Optional[float] = None

CACHE_SECONDS = int(os.getenv("PNL_CACHE_SECONDS", "5"))

def _headers():
    if not (ALPACA_KEY and ALPACA_SECRET):
        raise RuntimeError("Alpaca credentials missing for PnL (set ALPACA_API_KEY_ID and ALPACA_SECRET_KEY)")
    return {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _fetch_account() -> Tuple[float, float]:
    """Return (last_equity, equity) as floats. last_equity is prior trading day end."""
    import json
    url = f"{ALPACA_BASE}/account"
    r = requests.get(url, headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    try:
        leq = float(data.get("last_equity")) if data.get("last_equity") is not None else None
        eq  = float(data.get("equity")) if data.get("equity") is not None else None
    except Exception:
        raise RuntimeError(f"Unexpected /account payload: {json.dumps(data)[:400]}")
    if leq is None or eq is None:
        raise RuntimeError("Account missing last_equity/equity")
    return leq, eq

def get_daily_loss() -> Tuple[float, float, float]:
    """
    Returns (daily_loss, last_equity, equity).
    daily_loss = max(0, last_equity - equity). Positive = drawdown vs prior day close.
    """
    global _last_fetch_ts, _last_equity, _equity
    now = time.time()
    if now - _last_fetch_ts > CACHE_SECONDS or _last_equity is None or _equity is None:
        leq, eq = _fetch_account()
        _last_equity, _equity = leq, eq
        _last_fetch_ts = now
    loss = max(0.0, float(_last_equity) - float(_equity))
    return loss, float(_last_equity), float(_equity)
