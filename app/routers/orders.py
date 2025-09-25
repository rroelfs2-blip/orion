from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal, Dict, Any, List

from fastapi import APIRouter
from pydantic import BaseModel, field_validator, constr, conint, confloat
from dotenv import load_dotenv

load_dotenv(override=True)

router = APIRouter(tags=["orders"])

# ---------- Models ----------

Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]

class OrderPreviewRequest(BaseModel):
    symbol: constr(strip_whitespace=True, to_upper=True, min_length=1)
    side: Side
    qty: conint(strict=True, ge=1)
    order_type: OrderType = "market"
    limit_price: Optional[confloat(gt=0)] = None
    price_estimate: Optional[confloat(gt=0)] = None  # for market notional

    # Optional metadata; tests/dev can pass overrides here
    # meta = { "overrides": { "MAX_POSITION_RISK": 10, "ORDER_THROTTLE_SECONDS": 60,
    #                         "FORCE_THROTTLE_BLOCK": 1, "FORCE_COOLOFF_BLOCK": 1, ... } }
    meta: Optional[Dict[str, Any]] = None

    @field_validator("limit_price")
    @classmethod
    def limit_required_for_limit_orders(cls, v, info):
        if info.data.get("order_type") == "limit" and v is None:
            raise ValueError("limit_price is required for limit orders")
        return v


class RiskCheckResult(BaseModel):
    name: str
    passed: bool
    detail: Optional[str] = None


class OrderPreviewResponse(BaseModel):
    ok: bool
    status: Literal["PASSED", "PASSED_WITH_WARNINGS", "BLOCKED"]
    symbol: str
    side: Side
    qty: int
    order_type: OrderType
    notional_estimate: Optional[float] = None
    checks: List[RiskCheckResult]
    audit_id: str
    timestamp_utc: str


# ---------- Dynamic env & paths (NO import-time caching) ----------

ENV_KEYS = (
    "APP_NAME",
    "LOG_DIR",
    "CONFIG_DIR",
    "AUDIT_LOG_PATH",
    "DAILY_LOSS_LIMIT",
    "MAX_POSITION_RISK",
    "ORDER_THROTTLE_SECONDS",
    "COOLOFF_AFTER_DRAWDOWN",
    "SESSION_ENABLED",
    # test/dev only force flags (not stored in env; still allowed as overrides)
    "FORCE_THROTTLE_BLOCK",
    "FORCE_COOLOFF_BLOCK",
)

def _env(overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # Read from environment each call; apply optional per-request overrides last.
    e: Dict[str, Any] = {
        "APP_NAME": os.getenv("APP_NAME", "orion-backend"),
        "LOG_DIR": os.getenv("LOG_DIR", r"C:\AI files\Orion\orion-backend\logs"),
        "CONFIG_DIR": os.getenv("CONFIG_DIR", r"C:\AI files\Orion\orion-backend\config"),
        "AUDIT_LOG_PATH": os.getenv("AUDIT_LOG_PATH"),  # may be None; fallback below
        "DAILY_LOSS_LIMIT": float(os.getenv("DAILY_LOSS_LIMIT", "100.0")),
        "MAX_POSITION_RISK": float(os.getenv("MAX_POSITION_RISK", "50.0")),
        "ORDER_THROTTLE_SECONDS": int(os.getenv("ORDER_THROTTLE_SECONDS", "5")),
        "COOLOFF_AFTER_DRAWDOWN": int(os.getenv("COOLOFF_AFTER_DRAWDOWN", "1")),
        "SESSION_ENABLED": int(os.getenv("SESSION_ENABLED", "1")),
        # default off for force flags
        "FORCE_THROTTLE_BLOCK": 0,
        "FORCE_COOLOFF_BLOCK": 0,
    }
    if overrides:
        for k, v in overrides.items():
            if k not in ENV_KEYS:
                continue
            if k in {"DAILY_LOSS_LIMIT", "MAX_POSITION_RISK"}:
                e[k] = float(v)
            elif k in {"ORDER_THROTTLE_SECONDS", "COOLOFF_AFTER_DRAWDOWN", "SESSION_ENABLED",
                       "FORCE_THROTTLE_BLOCK", "FORCE_COOLOFF_BLOCK"}:
                e[k] = int(v)
            else:
                e[k] = v
    return e

def _paths(e: Dict[str, Any]) -> Dict[str, str]:
    log_dir = e["LOG_DIR"]
    cfg_dir = e["CONFIG_DIR"]
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg_dir).mkdir(parents=True, exist_ok=True)
    audit_path = e.get("AUDIT_LOG_PATH") or os.path.join(log_dir, "audit.jsonl")
    return {
        "LOG_DIR": log_dir,
        "CONFIG_DIR": cfg_dir,
        "AUDIT_LOG_PATH": audit_path,
        "LAST_ORDER_TS_FILE": os.path.join(log_dir, "last_order_ts.txt"),
        "COOLOFF_FLAG_FILE": os.path.join(cfg_dir, "cooloff_active.flag"),
    }

# ---------- Utilities ----------

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _read_last_order_ts(path: str) -> Optional[float]:
    try:
        txt = Path(path).read_text(encoding="utf-8").strip()
        return float(txt) if txt else None
    except FileNotFoundError:
        return None
    except Exception:
        return None

def _cooloff_active(flag_path: str, enforce_flag: int) -> bool:
    return enforce_flag == 1 and Path(flag_path).exists()

def _estimate_notional(req: OrderPreviewRequest) -> Optional[float]:
    if req.order_type == "limit" and req.limit_price:
        return float(req.qty) * float(req.limit_price)
    if req.order_type == "market" and req.price_estimate:
        return float(req.qty) * float(req.price_estimate)
    return None

def _append_audit(audit_path: str, entry: Dict[str, Any]) -> str:
    Path(os.path.dirname(audit_path)).mkdir(parents=True, exist_ok=True)
    audit_id = f"{int(time.time()*1000)}-{os.getpid()}"
    entry = {"audit_id": audit_id, **entry}
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return audit_id

# ---------- Risk evaluation (uses dynamic env) ----------

def evaluate_risk(req: OrderPreviewRequest, e: Dict[str, Any], p: Dict[str, str]) -> List[RiskCheckResult]:
    checks: List[RiskCheckResult] = []

    # 0) Force-blocks for deterministic tests/dev
    if int(e.get("FORCE_COOLOFF_BLOCK", 0)) == 1:
        checks.append(RiskCheckResult(name="cooloff", passed=False, detail="Forced cool-off block"))
    if int(e.get("FORCE_THROTTLE_BLOCK", 0)) == 1:
        checks.append(RiskCheckResult(name="throttle", passed=False, detail="Forced throttle block"))

    # 1) Session enabled
    if e["SESSION_ENABLED"] != 1:
        checks.append(RiskCheckResult(name="session_enabled", passed=False, detail="Session disabled"))
    else:
        checks.append(RiskCheckResult(name="session_enabled", passed=True))

    # 2) Cool-off after drawdown
    if not any(c.name == "cooloff" and not c.passed for c in checks):  # skip real check if forced
        if _cooloff_active(p["COOLOFF_FLAG_FILE"], e["COOLOFF_AFTER_DRAWDOWN"]):
            checks.append(RiskCheckResult(name="cooloff", passed=False, detail="Cool-off active"))
        else:
            checks.append(RiskCheckResult(name="cooloff", passed=True))

    # 3) Throttle
    if not any(c.name == "throttle" and not c.passed for c in checks):  # skip real check if forced
        last_ts = _read_last_order_ts(p["LAST_ORDER_TS_FILE"])
        if last_ts is not None:
            elapsed = time.time() - last_ts
            if elapsed < e["ORDER_THROTTLE_SECONDS"]:
                checks.append(RiskCheckResult(
                    name="throttle",
                    passed=False,
                    detail=f"Throttle: wait {e['ORDER_THROTTLE_SECONDS'] - int(elapsed)}s"
                ))
            else:
                checks.append(RiskCheckResult(name="throttle", passed=True, detail=f"Elapsed {int(elapsed)}s"))
        else:
            checks.append(RiskCheckResult(name="throttle", passed=True, detail="No prior order timestamp"))

    # 4) Per-position risk
    notional = _estimate_notional(req)
    if notional is None:
        checks.append(RiskCheckResult(
            name="max_position_risk",
            passed=True,
            detail="Notional unknown (no limit_price / price_estimate); skipped strict check"
        ))
    else:
        if notional > e["MAX_POSITION_RISK"]:
            checks.append(RiskCheckResult(
                name="max_position_risk",
                passed=False,
                detail=f"Notional {notional:.2f} exceeds MAX_POSITION_RISK {e['MAX_POSITION_RISK']:.2f}"
            ))
        else:
            checks.append(RiskCheckResult(
                name="max_position_risk",
                passed=True,
                detail=f"Notional {notional:.2f} ≤ {e['MAX_POSITION_RISK']:.2f}"
            ))

    # 5) Daily loss limit — enforced when PnL available
    from app.services.pnl_source import get_day_pnl  # local import to avoid cycles at startup
    day_pnl = get_day_pnl(p["LOG_DIR"])
    if day_pnl is None:
        checks.append(RiskCheckResult(
            name="daily_loss_limit",
            passed=True,
            detail=f"PnL unknown; limit {e['DAILY_LOSS_LIMIT']:.2f} not enforced"
        ))
    else:
        if day_pnl <= -abs(e["DAILY_LOSS_LIMIT"]):
            checks.append(RiskCheckResult(
                name="daily_loss_limit",
                passed=False,
                detail=f"Day PnL {day_pnl:.2f} ≤ -{e['DAILY_LOSS_LIMIT']:.2f} (blocked)"
            ))
        else:
            checks.append(RiskCheckResult(
                name="daily_loss_limit",
                passed=True,
                detail=f"Day PnL {day_pnl:.2f} within limit {e['DAILY_LOSS_LIMIT']:.2f}"
            ))

    return checks

def _final_status(checks: List[RiskCheckResult]) -> Literal["PASSED", "PASSED_WITH_WARNINGS", "BLOCKED"]:
    any_fail = any(not c.passed for c in checks)
    if any_fail:
        return "BLOCKED"
    warn = any(c.name == "max_position_risk" and "skipped" in (c.detail or "").lower() for c in checks)
    return "PASSED_WITH_WARNINGS" if warn else "PASSED"

# ---------- Routes ----------

@router.post("/orders/preview", response_model=OrderPreviewResponse, status_code=200)
def orders_preview(req: OrderPreviewRequest):
    """
    DRY-RUN ONLY: evaluates risk gates and writes an audit line.
    Does NOT submit to any broker. Does NOT update throttle state.
    """
    overrides = (req.meta or {}).get("overrides") if req.meta else None
    e = _env(overrides=overrides)
    p = _paths(e)

    checks = evaluate_risk(req, e, p)
    status_final = _final_status(checks)
    notional = _estimate_notional(req)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "app": e["APP_NAME"],
        "kind": "orders.preview",
        "request": req.model_dump(),
        "result": {
            "status": status_final,
            "checks": [c.model_dump() for c in checks],
            "notional_estimate": notional,
        },
        "paths": p,
        "overrides": overrides or {},
    }
    audit_id = _append_audit(p["AUDIT_LOG_PATH"], entry)

    any_fail = any(not c.passed for c in checks)
    ok = not any_fail  # explicit

    return OrderPreviewResponse(
        ok=ok,
        status=status_final,
        symbol=req.symbol,
        side=req.side,
        qty=req.qty,
        order_type=req.order_type,
        notional_estimate=notional,
        checks=checks,
        audit_id=audit_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
    )

@router.get("/orders/schema", tags=["orders"])
def orders_schema():
    e = _env()
    p = _paths(e)
    return {
        "request": OrderPreviewRequest.model_json_schema(),
        "response": OrderPreviewResponse.model_json_schema(),
        "notes": [
            "For market orders, include price_estimate to enable strict MAX_POSITION_RISK check.",
            "Use meta.overrides to force specific risk values during tests/dev.",
            "This endpoint never places an order and does not update throttle state.",
            f"Audit log: {p['AUDIT_LOG_PATH']}",
        ],
        "env": {
            "MAX_POSITION_RISK": e["MAX_POSITION_RISK"],
            "ORDER_THROTTLE_SECONDS": e["ORDER_THROTTLE_SECONDS"],
            "COOLOFF_AFTER_DRAWDOWN": e["COOLOFF_AFTER_DRAWDOWN"],
            "SESSION_ENABLED": e["SESSION_ENABLED"],
            "DAILY_LOSS_LIMIT": e["DAILY_LOSS_LIMIT"],
        },
    }
