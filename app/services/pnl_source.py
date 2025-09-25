# File: backend/app/services/pnl_source.py
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

def _coerce_float(val: str | float | int | None) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None

def get_day_pnl(log_dir: str) -> Optional[float]:
    """
    Return current day PnL as a float (positive = profit, negative = loss).
    Priority:
      1) ENV override: PNL_OVERRIDE (string/number)
      2) File JSON: { "day_pnl": <float> } at <LOG_DIR>/pnl.json
      3) None (unknown)
    """
    # 1) ENV override
    env_pnl = _coerce_float(os.getenv("PNL_OVERRIDE"))
    if env_pnl is not None:
        return env_pnl

    # 2) File source
    path = Path(log_dir) / "pnl.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _coerce_float(data.get("day_pnl"))
        except Exception:
            return None

    # 3) unknown
    return None

def set_day_pnl(log_dir: str, value: float) -> str:
    """
    Save PnL to <LOG_DIR>/pnl.json for local dev/tests; returns path.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    path = Path(log_dir) / "pnl.json"
    payload = {"day_pnl": float(value)}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)
