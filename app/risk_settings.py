# File: backend/app/risk_settings.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any
import os, json, threading

# Persisted file (human-editable)
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(Path(__file__).resolve().parents[1] / "config")))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
RISK_JSON = CONFIG_DIR / "risk.json"

_lock = threading.Lock()

@dataclass
class RiskSettings:
    # Core gates
    SESSION_ACTIVE: bool = True
    COOL_OFF_ACTIVE: bool = False
    ORDER_THROTTLE_SECONDS: int = 2

    # Limits (USD)
    DAILY_LOSS_LIMIT: float = 0.0
    MAX_POSITION_RISK: float = 1000.0

    # Audit
    AUDIT_LOG_PATH: str = str(Path(__file__).resolve().parents[1] / "logs" / "audit.jsonl")

def _from_env_default() -> RiskSettings:
    def b(name: str, default: str) -> bool:
        return (os.getenv(name, default) or default).strip() in ("1", "true", "True", "YES", "yes")
    def i(name: str, default: str) -> int:
        try: return int(os.getenv(name, default))
        except: return int(default)
    def f(name: str, default: str) -> float:
        try: return float(os.getenv(name, default))
        except: return float(default)

    return RiskSettings(
        SESSION_ACTIVE=b("SESSION_ACTIVE", "1"),
        COOL_OFF_ACTIVE=b("COOL_OFF_ACTIVE", "0"),
        ORDER_THROTTLE_SECONDS=i("ORDER_THROTTLE_SECONDS", "2"),
        DAILY_LOSS_LIMIT=f("DAILY_LOSS_LIMIT", "0"),
        MAX_POSITION_RISK=f("MAX_POSITION_RISK", "1000"),
        AUDIT_LOG_PATH=os.getenv("AUDIT_LOG_PATH", str(Path(__file__).resolve().parents[1] / "logs" / "audit.jsonl")),
    )

def _load_disk() -> RiskSettings | None:
    if not RISK_JSON.exists():
        return None
    try:
        data = json.loads(RISK_JSON.read_text(encoding="utf-8"))
        return RiskSettings(**data)
    except Exception:
        return None

def get_settings() -> RiskSettings:
    with _lock:
        existing = _load_disk()
        if existing:
            return existing
        # Seed from env on first run
        rs = _from_env_default()
        RISK_JSON.write_text(json.dumps(asdict(rs), indent=2), encoding="utf-8")
        return rs

def save_settings(rs: RiskSettings) -> None:
    with _lock:
        RISK_JSON.write_text(json.dumps(asdict(rs), indent=2), encoding="utf-8")

def update_settings(changes: Dict[str, Any]) -> RiskSettings:
    rs = get_settings()
    # Apply only known fields (case-sensitive)
    for k, v in changes.items():
        if not hasattr(rs, k):
            continue
        # Coerce types roughly
        cur = getattr(rs, k)
        if isinstance(cur, bool):
            setattr(rs, k, str(v).strip() in ("1", "true", "True", "YES", "yes"))
        elif isinstance(cur, int):
            setattr(rs, k, int(v))
        elif isinstance(cur, float):
            setattr(rs, k, float(v))
        else:
            setattr(rs, k, str(v))
    save_settings(rs)
    return rs
