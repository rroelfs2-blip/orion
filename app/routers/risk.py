# File: app/routers/risk.py
from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.risk import (
    current_preset,
    update_preset,
    evaluate_order,
    set_cooloff,
    clear_circuit_breaker,
)

# IMPORTANT: prefix is ONLY "/risk" here.
# main.py includes this router with prefix="/api"
# => final paths become "/api/risk/*"
router = APIRouter(prefix="/risk", tags=["risk"])


class RiskPresetPatch(BaseModel):
    ORDER_THROTTLE_SECONDS: Optional[int] = Field(None, ge=0)
    ORDERS_PER_MIN_LIMIT: Optional[int] = Field(None, ge=1)
    MAX_POSITION_RISK: Optional[float] = Field(None, gt=0)
    DAILY_LOSS_LIMIT: Optional[float] = Field(None, ge=0)
    SESSION_ENABLED: Optional[bool] = None
    ALLOW_PREMARKET: Optional[bool] = None
    ALLOW_AFTERHOURS: Optional[bool] = None
    TIMEZONE: Optional[str] = None
    RTH_START: Optional[str] = None
    RTH_END: Optional[str] = None
    COOLOFF_AFTER_DRAWDOWN: Optional[int] = Field(None, ge=0)


@router.get("/state")
def risk_state() -> Dict[str, Any]:
    return {"ok": True, "preset": current_preset()}


@router.post("/update")
def risk_update(patch: RiskPresetPatch):
    p = update_preset(patch.model_dump(exclude_none=True))
    return {"ok": True, "preset": p}


class OrderPreview(BaseModel):
    symbol: str
    side: str
    qty: float
    order_type: str
    limit_price: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None


@router.post("/evaluate")
def evaluate(order: OrderPreview):
    overrides = (order.meta or {}).get("overrides", None)
    res = evaluate_order(
        order.symbol,
        order.side,
        order.qty,
        order.order_type,
        order.limit_price,
        overrides,
    )
    return res.to_dict()


@router.post("/cooloff/{active}")
def toggle_cooloff(active: bool):
    set_cooloff(active)
    return {"ok": True, "cooloff": active}


@router.post("/circuit/clear")
def circuit_clear():
    clear_circuit_breaker()
    return {"ok": True, "circuit": "cleared"}
