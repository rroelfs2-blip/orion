# File: app/core/usage.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import datetime as dt
from typing import List, Dict, Any

# Root of repo = app/core/../../
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
TOKENS_FILE = CONFIG_DIR / "tokens.json"

@dataclass
class TokenUsage:
    current_balance: float
    daily_used: List[float]  # last N days in same units as balance (e.g., USD or tokens)
    currency: str = "USD"    # or "TOKENS" if you prefer counts

    def avg_per_day(self) -> float:
        if not self.daily_used:
            return 0.0
        return float(sum(self.daily_used) / len(self.daily_used))

    def to_dict(self) -> Dict[str, Any]:
        # timezone-aware UTC (avoids utcnow() deprecation)
        now_utc = dt.datetime.now(dt.UTC)
        return {
            "current_balance": self.current_balance,
            "avg_per_day": self.avg_per_day(),
            "days": len(self.daily_used),
            "currency": self.currency,
            "daily_used": self.daily_used,
            "as_of": now_utc.isoformat().replace("+00:00", "Z"),
        }

DEFAULT = TokenUsage(current_balance=0.0, daily_used=[], currency="USD")

def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_usage() -> TokenUsage:
    try:
        if TOKENS_FILE.exists():
            data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
            return TokenUsage(
                current_balance=float(data.get("current_balance", 0.0)),
                daily_used=[float(x) for x in data.get("daily_used", [])],
                currency=str(data.get("currency", "USD")),
            )
    except Exception:
        # fall through to default on any parse/format error
        pass
    return DEFAULT

def save_usage(payload: Dict[str, Any]) -> TokenUsage:
    _ensure_config_dir()
    merged = {
        "current_balance": float(payload.get("current_balance", 0.0)),
        "daily_used": [float(x) for x in payload.get("daily_used", [])],
        "currency": str(payload.get("currency", "USD")),
    }
    TOKENS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return load_usage()
