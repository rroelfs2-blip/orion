# File: app/routers/usage.py
from __future__ import annotations

import os
import json
import datetime as dt
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/usage", tags=["usage"])

# ======================================================================
# Shared config & helpers
# ======================================================================

def _config_dir() -> Path:
    cfg = os.getenv("ORION_CONFIG_DIR")
    if cfg:
        p = Path(cfg)
    else:
        p = Path(r"C:\AI files\Orion\orion-backend\config")
    p.mkdir(parents=True, exist_ok=True)
    return p

def _utc_now_iso() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"  # tests depended on utcnow()

def _utc_date_str(ts: Optional[dt.datetime] = None) -> str:
    t = ts or dt.datetime.utcnow()
    return t.strftime("%Y-%m-%d")

# ======================================================================
# TOKENS (already tested) — preserved
# ======================================================================

class TokensSetRequest(BaseModel):
    current_balance: float = Field(..., ge=0)
    daily_used: List[float] = Field(default_factory=list)
    currency: str = Field(default="USD", min_length=1, max_length=8)

class TokensState(BaseModel):
    current_balance: float
    daily_used: List[float]
    average_per_day: float
    currency: str
    as_of: str  # ISO8601 UTC '...Z'

def _tokens_path() -> Path:
    return _config_dir() / "usage_tokens.json"

def _compute_avg(daily: List[float]) -> float:
    if not daily:
        return 0.0
    return float(sum(daily) / len(daily))

def _read_tokens() -> Optional[dict]:
    path = _tokens_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def _write_tokens(data: dict) -> None:
    path = _tokens_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _state_from_raw(raw: Optional[dict]) -> TokensState:
    raw = raw or {}
    current_balance = float(raw.get("current_balance", 0.0))
    daily_used = [float(x) for x in raw.get("daily_used", [])]
    currency = str(raw.get("currency", "USD"))
    avg = _compute_avg(daily_used)
    as_of = raw.get("as_of") or _utc_now_iso()
    return TokensState(
        current_balance=current_balance,
        daily_used=daily_used,
        average_per_day=avg,
        currency=currency,
        as_of=as_of,
    )

def _usage_payload(state: TokensState) -> Dict[str, Any]:
    """
    Build a usage payload with compatibility aliases expected by tests/UI:
      - balance                -> current_balance
      - avg_per_day            -> average_per_day
      - average_used_per_day   -> average_per_day
      - days                   -> len(daily_used)
      - history / series       -> daily_used (aliases)
    """
    s = state.model_dump()
    usage = dict(s)
    usage["balance"] = usage["current_balance"]
    usage["avg_per_day"] = usage["average_per_day"]
    usage["average_used_per_day"] = usage["average_per_day"]
    usage["days"] = len(usage.get("daily_used", []))
    usage["history"] = usage.get("daily_used", [])
    usage["series"] = usage.get("daily_used", [])
    return usage

def _envelope(state: TokensState) -> Dict[str, Any]:
    # Tests expect top-level "usage". Keep "data" as an alias for compatibility.
    usage = _usage_payload(state)
    return {
        "ok": True,
        "usage": usage,
        "data": state.model_dump(),
    }

@router.get("/tokens")
def get_tokens() -> Dict[str, Any]:
    state = _state_from_raw(_read_tokens())
    return _envelope(state)

@router.post("/tokens/set")
def set_tokens(body: TokensSetRequest) -> Dict[str, Any]:
    payload = {
        "current_balance": body.current_balance,
        "daily_used": body.daily_used,
        "currency": body.currency,
        "as_of": _utc_now_iso(),
    }
    _write_tokens(payload)
    state = _state_from_raw(payload)
    return _envelope(state)

# ======================================================================
# COUNTERS + BILLING
# ======================================================================

class CountersAddRequest(BaseModel):
    service: str = Field(..., min_length=1)   # e.g., "openai:gpt-4o" or "oanda"
    tokens: Optional[float] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    requests: Optional[int] = Field(default=None, ge=0)
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD; defaults to today UTC")
    currency: str = Field(default="USD", min_length=1, max_length=8)

class CountersResetRequest(BaseModel):
    confirm: bool = Field(default=False)

def _counters_path() -> Path:
    return _config_dir() / "usage_counters.json"

def _read_counters() -> dict:
    path = _counters_path()
    if not path.exists():
        return {
            "as_of": _utc_now_iso(),
            "currency": "USD",
            "services": {},        # { service: { tokens, cost, requests } }
            "daily": {},           # { YYYY-MM-DD: { tokens, cost, requests } }
            "by_service_daily": {},# { service: { YYYY-MM-DD: { tokens, cost, requests } } }
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # If corrupt, start fresh
        return {
            "as_of": _utc_now_iso(),
            "currency": "USD",
            "services": {},
            "daily": {},
            "by_service_daily": {},
        }

def _write_counters(data: dict) -> None:
    data["as_of"] = _utc_now_iso()
    _counters_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _add_to_bucket(bucket: dict, key: str, tokens: float, cost: float, requests: int) -> None:
    entry = bucket.get(key) or {"tokens": 0.0, "cost": 0.0, "requests": 0}
    entry["tokens"] = float(entry.get("tokens", 0.0)) + tokens
    entry["cost"] = float(entry.get("cost", 0.0)) + cost
    entry["requests"] = int(entry.get("requests", 0)) + requests
    bucket[key] = entry

def _sum_entries(entries: List[dict]) -> dict:
    out = {"tokens": 0.0, "cost": 0.0, "requests": 0}
    for e in entries:
        out["tokens"] += float(e.get("tokens", 0.0))
        out["cost"] += float(e.get("cost", 0.0))
        out["requests"] += int(e.get("requests", 0))
    return out

def _last_n_days(n: int) -> List[str]:
    today = dt.datetime.utcnow().date()
    return [(today - dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)][::-1]

def _rollup_daily(counters: dict, days: int = 7) -> Tuple[dict, float]:
    # returns (per-day list, avg cost/day over window)
    seq = []
    selected = _last_n_days(days)
    for day in selected:
        d = counters.get("daily", {}).get(day, {})
        seq.append({
            "date": day,
            "tokens": float(d.get("tokens", 0.0)),
            "cost": float(d.get("cost", 0.0)),
            "requests": int(d.get("requests", 0)),
        })
    avg_cost = (sum(x["cost"] for x in seq) / days) if days > 0 else 0.0
    return ({"days": days, "series": seq}, avg_cost)

def _counters_envelope(counters: dict, window_days: int = 7) -> Dict[str, Any]:
    services = counters.get("services", {})
    daily = counters.get("daily", {})
    # totals
    total = _sum_entries([*services.values()])

    # 7-day rollup (cost avg/day)
    roll, avg_cost_per_day = _rollup_daily(counters, days=window_days)

    return {
        "ok": True,
        "summary": {
            "currency": counters.get("currency", "USD"),
            "as_of": counters.get("as_of", _utc_now_iso()),
            "total": total,
            "avg_cost_per_day": avg_cost_per_day,
            "window_days": window_days,
        },
        "per_service": services,
        "daily": daily,
        "rollup": roll,
    }

@router.get("/counters")
def get_counters(window_days: int = Query(default=7, ge=1, le=60)) -> Dict[str, Any]:
    counters = _read_counters()
    return _counters_envelope(counters, window_days=window_days)

@router.get("/counters/history")
def get_counters_history(days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    counters = _read_counters()
    seq, _ = _rollup_daily(counters, days=days)
    return {"ok": True, "history": seq, "currency": counters.get("currency", "USD")}

@router.post("/counters/add")
def add_counters(body: CountersAddRequest) -> Dict[str, Any]:
    date_key = body.date or _utc_date_str()
    tokens = float(body.tokens or 0.0)
    cost = float(body.cost or 0.0)
    requests = int(body.requests or 0)

    if tokens == 0.0 and cost == 0.0 and requests == 0:
        raise HTTPException(status_code=400, detail="Nothing to add; provide at least one of tokens/cost/requests")

    c = _read_counters()
    # currency sticky: prefer explicit body.currency if given
    c["currency"] = body.currency or c.get("currency", "USD")

    # services
    services = c.get("services") or {}
    _add_to_bucket(services, body.service, tokens, cost, requests)
    c["services"] = services

    # daily overall
    daily = c.get("daily") or {}
    _add_to_bucket(daily, date_key, tokens, cost, requests)
    c["daily"] = daily

    # by_service_daily
    by_sd = c.get("by_service_daily") or {}
    svc_map = by_sd.get(body.service) or {}
    _add_to_bucket(svc_map, date_key, tokens, cost, requests)
    by_sd[body.service] = svc_map
    c["by_service_daily"] = by_sd

    _write_counters(c)
    return _counters_envelope(c)

@router.post("/counters/reset")
def reset_counters(body: CountersResetRequest) -> Dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=false; refusing to reset")
    empty = {
        "as_of": _utc_now_iso(),
        "currency": "USD",
        "services": {},
        "daily": {},
        "by_service_daily": {},
    }
    _write_counters(empty)
    return {"ok": True, "summary": {"currency": "USD", "as_of": empty["as_of"], "total": {"tokens": 0.0, "cost": 0.0, "requests": 0}}}

@router.get("/billing")
def get_billing(window_days: int = Query(default=30, ge=1, le=365)) -> Dict[str, Any]:
    c = _read_counters()
    # Totals
    total = _sum_entries([*c.get("services", {}).values()])
    # Window rollup
    roll, avg_cost = _rollup_daily(c, days=window_days)
    return {
        "ok": True,
        "currency": c.get("currency", "USD"),
        "total_cost": total.get("cost", 0.0),
        "total_tokens": total.get("tokens", 0.0),
        "total_requests": total.get("requests", 0),
        "avg_cost_per_day": avg_cost,
        "window": roll,
        "as_of": c.get("as_of", _utc_now_iso()),
    }
