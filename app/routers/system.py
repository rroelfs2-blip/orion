# File: backend/app/routers/system.py
from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter

router = APIRouter(tags=["system"])

SENSITIVE_SUBSTRINGS = (
    "SECRET", "TOKEN", "PASSWORD", "API_KEY", "KEY_ID", "PRIVATE", "CLIENT_SECRET",
    "AUTH", "BEARER", "SIGNING", "WEBHOOK", "SEED",
)

def _mask_value(val: str) -> str:
    if not val:
        return val
    if len(val) <= 8:
        return "*" * len(val)
    return f"{val[:4]}***{val[-4:]}"

def _is_sensitive_key(k: str) -> bool:
    ku = k.upper()
    return any(s in ku for s in SENSITIVE_SUBSTRINGS)

def masked_env_snapshot() -> Dict[str, Any]:
    env = dict(os.environ)
    out: Dict[str, Any] = {}

    whitelist = {
        "APP_ENV", "HOST", "PORT", "BASE_URL",
        "ALPACA_ENV", "ALPACA_BASE_URL",
        "ORION_VERSION", "STRATOGEN_VERSION",
        "CONFIG_DIR", "AUDIT_LOG_PATH", "LOG_DIR",
        "CORS_ALLOW_ORIGINS",
    }
    for k, v in env.items():
        if k in whitelist:
            out[k] = v
        elif _is_sensitive_key(k):
            out[k] = _mask_value(v)
        else:
            if k in {"SESSION_ENABLED", "DAILY_LOSS_LIMIT", "MAX_POSITION_RISK", "ORDER_THROTTLE_SECONDS", "COOLOFF_AFTER_DRAWDOWN"}:
                out[k] = v

    return out

@router.get("/system/health")
def system_health():
    return {
        "ok": True,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "app": os.getenv("APP_NAME", "orion-backend"),
        "version": os.getenv("ORION_VERSION", os.getenv("STRATOGEN_VERSION", "unknown")),
    }

@router.get("/system/env")
def system_env():
    return {
        "ok": True,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "env": masked_env_snapshot(),
    }
