# File: backend/app/risk_engine.py

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json, threading

from app import pnl_service
from app.risk_settings import get_settings

_last_order_lock = threading.Lock()
_last_order_time: Optional[datetime] = None

@dataclass
class RiskResult:
    ok: bool
    reasons: List[str]
    gates: Dict[str, bool]
    context: Dict[str, Any]

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _audit_path() -> Path:
    # derive from current settings each time
    return Path(get_settings().AUDIT_LOG_PATH)

def write_audit(event: Dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _now_iso(), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def evaluate_order(symbol: str, side: str, qty: float, price: Optional[float]) -> RiskResult:
    s = get_settings()
    reasons: List[str] = []
    gates: Dict[str, bool] = {}
    ctx: Dict[str, Any] = {}

    # 1) session on?
    gates["session_active"] = s.SESSION_ACTIVE
    if not s.SESSION_ACTIVE:
        reasons.append("Session is not active")

    # 2) cool-off?
    gates["cool_off"] = not s.COOL_OFF_ACTIVE
    if s.COOL_OFF_ACTIVE:
        reasons.append("Cool-off active")

    # 3) throttle
    global _last_order_time
    with _last_order_lock:
        if s.ORDER_THROTTLE_SECONDS > 0 and _last_order_time is not None:
            delta = (datetime.utcnow() - _last_order_time).total_seconds()
            if delta < s.ORDER_THROTTLE_SECONDS:
                gates["throttle_ok"] = False
                reasons.append(f"Order throttled ({s.ORDER_THROTTLE_SECONDS - int(delta)}s remaining)")
            else:
                gates["throttle_ok"] = True
        else:
            gates["throttle_ok"] = True

    # 4) per-order risk cap
    if s.MAX_POSITION_RISK > 0 and price is not None and qty is not None:
        order_risk = abs(qty) * float(price)
        ctx["order_risk"] = order_risk
        gates["per_order_risk_ok"] = order_risk <= s.MAX_POSITION_RISK
        if not gates["per_order_risk_ok"]:
            reasons.append(f"Per-order risk {order_risk:.2f} exceeds cap {s.MAX_POSITION_RISK:.2f}")
    else:
        gates["per_order_risk_ok"] = True

    # 5) daily loss limit
    if s.DAILY_LOSS_LIMIT > 0:
        try:
            loss, last_eq, eq = pnl_service.get_daily_loss()
            ctx["pnl"] = {"loss": loss, "last_equity": last_eq, "equity": eq}
            gates["daily_loss_limit_ok"] = loss <= s.DAILY_LOSS_LIMIT
            if not gates["daily_loss_limit_ok"]:
                reasons.append(f"Daily loss {loss:.2f} exceeds limit {s.DAILY_LOSS_LIMIT:.2f}")
        except Exception as e:
            gates["daily_loss_limit_ok"] = False
            reasons.append(f"PnL unavailable: {e}")
    else:
        gates["daily_loss_limit_ok"] = True

    ok = all(gates.values())
    return RiskResult(ok=ok, reasons=reasons, gates=gates, context=ctx)

def mark_order_sent() -> None:
    global _last_order_time
    with _last_order_lock:
        _last_order_time = datetime.utcnow()
