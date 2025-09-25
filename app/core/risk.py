from __future__ import annotations
import json, os, time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from app.core.settings import settings

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = (BASE_DIR / "logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
CFG_DIR = (BASE_DIR / "config"); CFG_DIR.mkdir(parents=True, exist_ok=True)

LAST_ORDER_TS_FILE = LOG_DIR / "last_order_ts.txt"
ORDERS_AUDIT_FILE = LOG_DIR / "orders_audit.jsonl"
COOLOFF_FLAG_FILE = CFG_DIR / "cooloff_active.flag"
RISK_PRESET_FILE = CFG_DIR / "risk_preset.json"
CIRCUIT_BREAKER_FILE = CFG_DIR / "circuit_breaker.lock"
HOLIDAY_FILE = CFG_DIR / "us_holidays.json"

DEFAULT_PRESET = {
    "ORDER_THROTTLE_SECONDS": settings.ORDER_THROTTLE_SECONDS,
    "ORDERS_PER_MIN_LIMIT": settings.ORDERS_PER_MIN_LIMIT,
    "MAX_POSITION_RISK": settings.MAX_POSITION_RISK,
    "DAILY_LOSS_LIMIT": settings.DAILY_LOSS_LIMIT,
    "SESSION_ENABLED": True,
    "ALLOW_PREMARKET": False,
    "ALLOW_AFTERHOURS": False,
    "TIMEZONE": settings.SESSION_TZ,
    "RTH_START": "09:30",
    "RTH_END": "16:00",
    "COOLOFF_AFTER_DRAWDOWN": settings.COOLOFF_AFTER_DRAWDOWN,
}

_rolling_min_buckets: Dict[int, int] = {}

def _now_utc(): return datetime.now(timezone.utc)
def _read_float(path: Path):
    try: return float(path.read_text(encoding="utf-8").strip())
    except Exception: return None
def _write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
def _append_jsonl(path: Path, obj: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f: f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _is_us_holiday(d: datetime) -> bool:
    try:
        if HOLIDAY_FILE.exists():
            days = json.loads(HOLIDAY_FILE.read_text(encoding="utf-8"))
            return d.strftime("%Y-%m-%d") in set(days)
    except Exception: pass
    y = d.year
    return d.strftime("%Y-%m-%d") in {f"{y}-01-01", f"{y}-07-04", f"{y}-12-25"}

def _is_rth_open(now_et: datetime, preset: Dict[str, Any]) -> bool:
    start = preset.get("RTH_START", "09:30"); end = preset.get("RTH_END", "16:00")
    hhmm = now_et.strftime("%H:%M"); return start <= hhmm <= end

def _get_preset() -> Dict[str, Any]:
    if RISK_PRESET_FILE.exists():
        try: return {**DEFAULT_PRESET, **json.loads(RISK_PRESET_FILE.read_text(encoding="utf-8"))}
        except Exception: return DEFAULT_PRESET.copy()
    return DEFAULT_PRESET.copy()

def _save_preset(p): _write_text(RISK_PRESET_FILE, json.dumps(p, indent=2))

def _orders_in_last_minute() -> int:
    now = int(time.time()); minute = now // 60
    for k in list(_rolling_min_buckets.keys()):
        if k < minute - 1: _rolling_min_buckets.pop(k, None)
    return _rolling_min_buckets.get(minute, 0)

def _bump_orders_minute_counter():
    now = int(time.time()); minute = now // 60
    _rolling_min_buckets[minute] = _rolling_min_buckets.get(minute, 0) + 1

from typing import Dict as _Dict
@dataclass
class RiskCheckResult:
    ok: bool
    reasons: _Dict[str, Any]
    preset: _Dict[str, Any]
    def to_dict(self) -> _Dict[str, Any]:
        d = asdict(self); d["blocked"] = not self.ok; return d

def current_preset() -> Dict[str, Any]: return _get_preset()
def update_preset(patch: Dict[str, Any]) -> Dict[str, Any]:
    p = _get_preset(); p.update({k: v for k, v in patch.items() if k in DEFAULT_PRESET}); _save_preset(p); return p
def clear_circuit_breaker():
    if CIRCUIT_BREAKER_FILE.exists(): CIRCUIT_BREAKER_FILE.unlink(missing_ok=True)
def set_cooloff(active: bool):
    if active: _write_text(COOLOFF_FLAG_FILE, "1")
    else:
        if COOLOFF_FLAG_FILE.exists(): COOLOFF_FLAG_FILE.unlink(missing_ok=True)

def evaluate_order(symbol: str, side: str, qty: float, order_type: str, price: Optional[float], meta_overrides=None) -> RiskCheckResult:
    preset = _get_preset(); 
    if meta_overrides: preset = {**preset, **meta_overrides}
    now_utc = _now_utc(); now_et = now_utc - timedelta(hours=4)  # naive ET

    session_ok = True; session_reason = "ok"
    if bool(preset.get("SESSION_ENABLED", True)):
        if _is_us_holiday(now_et): session_ok = False; session_reason = "holiday"
        elif not _is_rth_open(now_et, preset) and not (preset.get("ALLOW_PREMARKET") or preset.get("ALLOW_AFTERHOURS")):
            session_ok = False; session_reason = "closed"

    throttle_secs = int(preset.get("ORDER_THROTTLE_SECONDS", 3))
    last_ts = _read_float(LAST_ORDER_TS_FILE) or 0.0
    throttle_ok = True; throttle_reason = "ok"
    if throttle_secs > 0 and last_ts and (time.time() - last_ts) < throttle_secs:
        throttle_ok = False; throttle_reason = "throttled"

    opm_limit = int(preset.get("ORDERS_PER_MIN_LIMIT", 15))
    opm_now = _orders_in_last_minute()
    opm_ok = opm_now < opm_limit; opm_reason = f"{opm_now}/{opm_limit}" if not opm_ok else "ok"

    notional = (price or 0.0) * float(qty or 0.0)
    max_pos = float(preset.get("MAX_POSITION_RISK", 2500.0))
    notional_ok = notional <= max_pos if max_pos > 0 else True
    notional_reason = f"{notional:.2f}>{max_pos:.2f}" if not notional_ok else "ok"

    daily_pnl_file = LOG_DIR / "daily_pnl_now.txt"
    val = _read_float(daily_pnl_file) or 0.0
    daily_limit = float(preset.get("DAILY_LOSS_LIMIT", 500.0))
    daily_ok = True; daily_reason = "ok"
    if daily_limit > 0 and val < -abs(daily_limit): daily_ok = False; daily_reason = f"breach {val:.2f} < {-abs(daily_limit):.2f}"
    if (LOG_DIR / 'circuit_breaker.lock').exists(): daily_ok = False; daily_reason = "circuit_breaker"

    cooloff_ok = not COOLOFF_FLAG_FILE.exists()
    cooloff_reason = "ok" if cooloff_ok else "cooloff_active"

    all_ok = session_ok and throttle_ok and opm_ok and notional_ok and daily_ok and cooloff_ok
    reasons = {"session": session_reason, "throttle": throttle_reason, "orders_per_min": opm_reason,
               "max_position_risk": notional_reason, "daily_loss_limit": daily_reason, "cooloff": cooloff_reason,
               "notional": notional, "qty": qty, "price": price}

    audit = {"ts": datetime.now().isoformat(timespec="seconds"), "symbol": symbol, "side": side, "qty": qty, "type": order_type,
             "price": price, "notional": notional, "reasons": reasons, "result": "ALLOW" if all_ok else "BLOCK",
             "preset": {k: preset.get(k) for k in DEFAULT_PRESET.keys()}}
    _append_jsonl(ORDERS_AUDIT_FILE, audit)

    if all_ok:
        _write_text(LAST_ORDER_TS_FILE, str(time.time())); _bump_orders_minute_counter()
    else:
        if reasons["daily_loss_limit"] != "ok": _write_text(LOG_DIR / 'circuit_breaker.lock', 'daily_breach')
        if preset.get("COOLOFF_AFTER_DRAWDOWN", 0) and reasons["daily_loss_limit"] != "ok":
            _write_text(COOLOFF_FLAG_FILE, "1")

    return RiskCheckResult(ok=all_ok, reasons=reasons, preset=preset)
