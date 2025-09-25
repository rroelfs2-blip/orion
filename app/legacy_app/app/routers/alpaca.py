# src/app/routers/alpaca.py
from fastapi import APIRouter, HTTPException, Query
import os, json, sqlite3
import httpx
from typing import Optional, Literal, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
from math import floor

router = APIRouter(prefix="/alpaca", tags=["alpaca"])

JOURNAL_DB = os.getenv("JOURNAL_DB", "journal.db")

# ---------- SQLite helpers/migrations ----------
def _connect():
    con = sqlite3.connect(JOURNAL_DB, timeout=30, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=5000;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

def _ensure_columns(con: sqlite3.Connection, table: str, cols: List[Tuple[str, str]]):
    for name, typ in cols:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column name" in msg:  # already there
                continue
            if "no such table" in msg:          # table created later below
                continue
            raise
    con.commit()

def _migrate(con: sqlite3.Connection):
    # Core tables
    con.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            order_id TEXT,
            symbol TEXT,
            side TEXT,
            qty REAL,
            price REAL,
            avg_fill_price REAL,
            status TEXT,
            note TEXT,
            payload TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ts TEXT NOT NULL,
            end_ts   TEXT,
            status   TEXT NOT NULL,      -- active | stopped | expired
            budget_total REAL NOT NULL,
            duration_min INTEGER,
            note TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            order_id TEXT,
            symbol TEXT,
            side TEXT,
            est_price REAL,
            qty REAL,
            amount REAL,
            filled_qty REAL,
            avg_fill_price REAL,
            status TEXT NOT NULL,         -- open | spent | released
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_symbol_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            max_dollars REAL,
            max_shares REAL,
            UNIQUE(session_id, symbol),
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS auto_session (
            id INTEGER PRIMARY KEY CHECK (id=1),
            enabled INTEGER DEFAULT 0
        )
    """)
    # Universe (symbols you allow yourself to trade)
    con.execute("""
        CREATE TABLE IF NOT EXISTS universe_symbols (
            symbol TEXT PRIMARY KEY,
            note TEXT,
            active INTEGER DEFAULT 1
        )
    """)
    con.commit()

    # Late-added columns
    _ensure_columns(con, "session_reservations", [
        ("filled_qty", "REAL"),
        ("avg_fill_price", "REAL"),
    ])
    _ensure_columns(con, "auto_session", [
        ("budget_total", "REAL"),
        ("duration_min", "INTEGER"),
        ("start_hour", "INTEGER"),
        ("start_min",  "INTEGER"),
        ("last_started_date", "TEXT"),
    ])

    # Defaults
    con.execute("INSERT OR IGNORE INTO auto_session (id, enabled) VALUES (1, 0)")
    con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('trading_mode','paper')")
    con.commit()

def _db() -> sqlite3.Connection:
    con = _connect()
    _migrate(con)
    return con

# ---------- misc helpers ----------
def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc, microsecond=0).isoformat().replace("+00:00","Z")

def f(x, default=0.0) -> float:
    try: return float(x)
    except Exception: return float(default)

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    con = _db()
    cur = con.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    con = _db()
    con.execute("""
        INSERT INTO settings(key,value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    con.commit(); con.close()

def trading_mode() -> str:
    return (get_setting("trading_mode", "paper") or "paper").lower()

def trading_base() -> str:
    if trading_mode() == "live":
        return os.getenv("ALPACA_TRADING_BASE_LIVE", "https://api.alpaca.markets/v2")
    return os.getenv("ALPACA_TRADING_BASE", "https://paper-api.alpaca.markets/v2")

def data_base() -> str:
    # Stocks v2 base (we keep for equities)
    return os.getenv("ALPACA_DATA_BASE", "https://data.alpaca.markets/v2")

def data_root() -> str:
    # Root domain used to reach crypto v1beta3 endpoints
    return os.getenv("ALPACA_DATA_ROOT", "https://data.alpaca.markets")

def alpaca_headers() -> Dict[str, str]:
    k = os.getenv("ALPACA_KEY"); s = os.getenv("ALPACA_SECRET")
    if not k or not s:
        raise HTTPException(status_code=500, detail="Missing ALPACA_KEY/ALPACA_SECRET in env")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}

async def latest_price(symbol: str, feed: str = "iex") -> Optional[float]:
    sym = symbol.upper()
    # Detect crypto pairs (contain slash)
    if "/" in sym:
        url = f"{data_root()}/v1beta3/crypto/us/snapshots"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=alpaca_headers(), params={"symbols": sym})
            r.raise_for_status()
            data = r.json() or {}
        snap = ((data.get("snapshots") or {}).get(sym)) or {}
        t = snap.get("latestTrade") or {}
        q = snap.get("latestQuote") or {}
        p = t.get("p") or q.get("ap") or q.get("bp")
        try:
            return float(p)
        except Exception:
            return None
    # Stocks path
    url = f"{data_base()}/stocks/{sym}/snapshot"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=alpaca_headers(), params={"feed": feed})
        r.raise_for_status()
        data = r.json()
    t = (data or {}).get("latestTrade") or {}
    q = (data or {}).get("latestQuote") or {}
    p = t.get("p") or q.get("ap") or q.get("bp")
    return float(p) if isinstance(p, (int, float)) else None

# ---------- journal ----------
def log_entry(kind: str, **kw):
    con = _db()
    con.execute(
        """INSERT INTO entries (ts, kind, order_id, symbol, side, qty, price, avg_fill_price, status, note, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_utcnow_iso(), kind, kw.get("order_id"), kw.get("symbol"), kw.get("side"), kw.get("qty"),
         kw.get("price"), kw.get("avg_fill_price"), kw.get("status"), kw.get("note"), kw.get("payload"))
    )
    con.commit(); con.close()

def list_entries(limit: int = 200) -> List[Dict[str, Any]]:
    con = _db()
    cur = con.execute("""SELECT id, ts, kind, order_id, symbol, side, qty, price, avg_fill_price, status, note
                         FROM entries ORDER BY id DESC LIMIT ?""", (limit,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close(); return rows

def list_entries_by_kind(kind: str, limit: int = 1000) -> List[Dict[str, Any]]:
    con = _db()
    cur = con.execute("""SELECT id, ts, kind, price, note, payload FROM entries
                         WHERE kind=? ORDER BY id DESC LIMIT ?""", (kind, limit))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close(); return rows

# ---------- session budget core ----------
def _get_active_session(con: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    cur = con.execute("""SELECT id, start_ts, end_ts, status, budget_total, duration_min, note
                         FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1""")
    row = cur.fetchone()
    if not row: return None
    s = dict(zip([c[0] for c in cur.description], row))
    if s.get("duration_min"):
        start_dt = datetime.fromisoformat(s["start_ts"].replace("Z","")).replace(tzinfo=timezone.utc)
        if datetime.utcnow().replace(tzinfo=timezone.utc) > start_dt + timedelta(minutes=int(s["duration_min"])):
            con.execute("UPDATE sessions SET status='expired', end_ts=? WHERE id=?", (_utcnow_iso(), s["id"]))
            con.commit()
            s["status"] = "expired"
    return s

def _sum_by(con: sqlite3.Connection, session_id: int, symbol: Optional[str], statuses: Tuple[str, ...], field: str) -> float:
    params = [session_id]
    sql = f"SELECT COALESCE(SUM({field}),0.0) FROM session_reservations WHERE session_id=? AND status IN ({','.join(['?']*len(statuses))})"
    params.extend(statuses)
    if symbol:
        sql += " AND symbol=?"; params.append(symbol)
    cur = con.execute(sql, tuple(params))
    return f(cur.fetchone()[0], 0.0)

def _session_summary(con: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    s = _get_active_session(con)
    if not s: return None
    total = f(s["budget_total"])
    open_amt = _sum_by(con, s["id"], None, ("open",), "amount")
    spent_amt = _sum_by(con, s["id"], None, ("spent",), "amount")
    remaining = max(0.0, total - open_amt - spent_amt)
    elapsed_sec = None; left_sec = None
    if s.get("duration_min"):
        start_dt = datetime.fromisoformat(s["start_ts"].replace("Z","")).replace(tzinfo=timezone.utc)
        end_dt   = start_dt + timedelta(minutes=int(s["duration_min"]))
        now      = datetime.utcnow().replace(tzinfo=timezone.utc)
        elapsed_sec = max(0, int((now - start_dt).total_seconds()))
        left_sec    = max(0, int((end_dt - now).total_seconds()))
    return {
        "id": s["id"], "status": s["status"], "start_ts": s["start_ts"], "end_ts": s["end_ts"],
        "budget_total": total, "open": open_amt, "spent": spent_amt, "remaining": remaining,
        "duration_min": s.get("duration_min"), "elapsed_sec": elapsed_sec, "left_sec": left_sec,
        "note": s.get("note")
    }

def _reserve(con: sqlite3.Connection, session_id: int, order_id: str,
             symbol: str, side: str, est_price: float, qty: float, amount: float):
    con.execute("""INSERT INTO session_reservations
                   (session_id, ts, order_id, symbol, side, est_price, qty, amount, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
                (session_id, _utcnow_iso(), order_id, symbol, side, est_price, qty, amount))
    con.commit()

def _release_by_order(con: sqlite3.Connection, order_id: str):
    con.execute("""UPDATE session_reservations SET status='released'
                   WHERE order_id=? AND status='open'""", (order_id,))
    con.commit()

def _spend_by_order(con: sqlite3.Connection, order_id: str, filled_qty: Optional[float], avg_fill_price: Optional[float]):
    if filled_qty and avg_fill_price:
        amt = f(filled_qty) * f(avg_fill_price)
        con.execute("""UPDATE session_reservations
                       SET status='spent', filled_qty=?, avg_fill_price=?, amount=?
                       WHERE order_id=? AND status='open'""",
                    (filled_qty, avg_fill_price, amt, order_id))
    else:
        con.execute("""UPDATE session_reservations
                       SET status='spent'
                       WHERE order_id=? AND status='open'""",
                    (order_id,))
    con.commit()

# ---- session endpoints ----
@router.post("/session/start")
async def session_start(budget: float, duration_min: Optional[int] = None, note: Optional[str] = None):
    if budget <= 0: raise HTTPException(400, "Budget must be > 0")
    con = _db()
    s = _get_active_session(con)
    if s and s["status"] == "active":
        con.execute("UPDATE sessions SET status='stopped', end_ts=? WHERE id=?", (_utcnow_iso(), s["id"]))
        con.commit()
    con.execute("""INSERT INTO sessions (start_ts, status, budget_total, duration_min, note)
                   VALUES (?, 'active', ?, ?, ?)""", (_utcnow_iso(), float(budget), duration_min, note))
    con.commit()
    sid = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
    con.close()
    return {"ok": True, "session_id": sid}

@router.post("/session/stop")
async def session_stop():
    con = _db()
    s = _get_active_session(con)
    if not s:
        con.close()
        return {"ok": True, "message": "no active session"}
    con.execute("UPDATE sessions SET status='stopped', end_ts=? WHERE id=?", (_utcnow_iso(), s["id"]))
    con.commit(); con.close()
    return {"ok": True, "stopped_session_id": s["id"]}

@router.get("/session")
async def session_status():
    con = _db()
    summary = _session_summary(con)
    con.close()
    if not summary: return {"active": False}
    if summary["status"] == "expired":
        return {"active": False, "expired": True, "summary": summary}
    return {"active": True, "summary": summary}

@router.get("/session/log")
async def session_log(limit: int = Query(500, ge=1, le=5000), latest_if_none: bool = True):
    con = _db()
    s = _get_active_session(con)
    sid = None
    if s:
        sid = s["id"]
    elif latest_if_none:
        cur = con.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        sid = row[0] if row else None
    if not sid:
        con.close()
        return {"session": None, "rows": [], "totals": {}}
    cur = con.execute("""
        SELECT ts, order_id, symbol, side, est_price, qty, amount, filled_qty, avg_fill_price, status
        FROM session_reservations
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (sid, limit))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    tot = {k: _sum_by(con, sid, None, (k,), "amount") for k in ("open","spent","released")}
    tot["count"] = len(rows)
    con.close()
    return {"session_id": sid, "rows": rows, "totals": tot}

# ---- symbol throttle endpoints ----
@router.post("/session/symbol_limit")
async def session_symbol_limit(symbol: str, max_dollars: Optional[float] = None, max_shares: Optional[float] = None):
    symbol = symbol.upper().strip()
    if not symbol: raise HTTPException(400, "symbol required")
    con = _db()
    s = _get_active_session(con)
    if not s or s["status"] != "active":
        con.close()
        raise HTTPException(400, "no active session")
    con.execute("""
        INSERT INTO session_symbol_limits (session_id, symbol, max_dollars, max_shares)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, symbol) DO UPDATE SET
            max_dollars=excluded.max_dollars,
            max_shares=excluded.max_shares
    """, (s["id"], symbol, max_dollars, max_shares))
    con.commit(); con.close()
    return {"ok": True}

@router.get("/session/symbol_limits")
async def session_symbol_limits():
    con = _db()
    s = _get_active_session(con)
    if not s or s["status"] != "active":
        con.close()
        return {"active": False, "limits": []}
    cur = con.execute("""SELECT symbol, max_dollars, max_shares
                         FROM session_symbol_limits WHERE session_id=? ORDER BY symbol""", (s["id"],))
    rows = [{"symbol": r[0], "max_dollars": r[1], "max_shares": r[2]} for r in cur.fetchall()]
    con.close()
    return {"active": True, "limits": rows}

@router.post("/session/symbol_limit/delete")
async def session_symbol_limit_delete(symbol: str):
    symbol = symbol.upper().strip()
    con = _db()
    s = _get_active_session(con)
    if not s or s["status"] != "active":
        con.close()
        raise HTTPException(400, "no active session")
    con.execute("""DELETE FROM session_symbol_limits WHERE session_id=? AND symbol=?""", (s["id"], symbol))
    con.commit(); con.close()
    return {"ok": True}

# ---- daily auto-session ----
@router.post("/session/auto/config")
async def auto_session_config(enabled: bool,
                              budget_total: Optional[float] = None,
                              duration_min: Optional[int] = None,
                              start_hour: Optional[int] = None,
                              start_min: Optional[int] = None):
    con = _db()
    con.execute("""UPDATE auto_session SET enabled=?, budget_total=?, duration_min=?, start_hour=?, start_min=? WHERE id=1""",
                (1 if enabled else 0, budget_total, duration_min, start_hour, start_min))
    con.commit(); con.close()
    return {"ok": True}

@router.get("/session/auto/config")
async def auto_session_get():
    con = _db()
    cur = con.execute("SELECT enabled, budget_total, duration_min, start_hour, start_min, last_started_date FROM auto_session WHERE id=1")
    row = cur.fetchone()
    con.close()
    if not row:
        return {"enabled": False}
    keys = ["enabled","budget_total","duration_min","start_hour","start_min","last_started_date"]
    data = dict(zip(keys, row))
    data["enabled"] = bool(data["enabled"])
    return data

@router.post("/session/auto/tick")
async def auto_session_tick():
    con = _db()
    cur = con.execute("SELECT enabled, budget_total, duration_min, start_hour, start_min, last_started_date FROM auto_session WHERE id=1")
    row = cur.fetchone()
    if not row:
        con.close()
        return {"ok": True, "started": False, "reason": "no config"}
    enabled, budget, duration, h, m, last_started = row
    if not enabled:
        con.close()
        return {"ok": True, "started": False, "reason": "disabled"}
    today = datetime.now().date().isoformat()
    now = datetime.now()
    if last_started == today:
        con.close()
        return {"ok": True, "started": False, "reason": "already started today"}
    if h is None or m is None or budget is None or budget <= 0:
        con.close()
        return {"ok": True, "started": False, "reason": "incomplete config"}
    start_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if now >= start_dt:
        s = _get_active_session(con)
        if not s or s["status"] != "active":
            con.execute("""INSERT INTO sessions (start_ts, status, budget_total, duration_min, note)
                           VALUES (?, 'active', ?, ?, ?)""",
                        (_utcnow_iso(), float(budget), duration, "auto-session"))
            con.execute("UPDATE auto_session SET last_started_date=? WHERE id=1", (today,))
            con.commit()
            con.close()
            return {"ok": True, "started": True}
    con.close()
    return {"ok": True, "started": False}

# ---- Trading Mode (paper/live) ----
CONFIRM_PHRASE = "I UNDERSTAND THE RISKS"

@router.get("/config/trading_mode")
async def get_trading_mode():
    mode = trading_mode()
    return {
        "mode": mode,
        "trading_base": trading_base(),
        "data_base": data_base(),
        "confirm_phrase": CONFIRM_PHRASE
    }

@router.post("/config/trading_mode")
async def set_trading_mode(mode: Literal["paper","live"], confirm_phrase: Optional[str] = None):
    mode = mode.lower()
    if mode == "live":
        if (confirm_phrase or "").strip() != CONFIRM_PHRASE:
            raise HTTPException(400, "To switch to LIVE, you must supply the exact confirm_phrase.")
        if "api.alpaca.markets" not in trading_base():
            raise HTTPException(400, f"Live mode requested but trading_base '{trading_base()}' is not a live endpoint.")
    set_setting("trading_mode", mode)
    return {"ok": True, "mode": trading_mode(), "trading_base": trading_base()}

# ---- Account / Clock ----
@router.get("/account")
async def account():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{trading_base()}/account", headers=alpaca_headers())
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Alpaca account error: {e!s}")

@router.get("/clock")
async def clock():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{trading_base()}/clock", headers=alpaca_headers())
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Alpaca clock error: {e!s}")

@router.post("/test-buy")
async def test_buy(symbol: str = "AAPL", qty: int = 1):
    body = {"symbol": symbol.upper(), "qty": qty, "side": "buy", "type": "market", "time_in_force": "day"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{trading_base()}/orders", headers=alpaca_headers(), json=body)
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            order = r.json()
            try: log_entry("order_submitted", order_id=order.get("id"), symbol=symbol.upper(), side="buy", qty=qty, status=order.get("status"), payload=json.dumps(order))
            except Exception: pass
            await client.delete(f"{trading_base()}/orders/{order['id']}", headers=alpaca_headers())
            try: log_entry("order_cancelled", order_id=order.get("id"), symbol=symbol.upper(), side="buy", qty=qty)
            except Exception: pass
            return {"ok": True, "order_id": order.get("id")}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Alpaca order error: {e!s}")

# ---- Market Data: Stocks Bars / Quotes ----
@router.get("/bars")
async def bars(
    symbol: str,
    timeframe: str = Query("1Day", description="e.g., 1Min,5Min,15Min,1Hour,1Day"),
    limit: int = Query(50, ge=1, le=1000),
    feed: str = Query("iex", description="iex (free) or sip (requires plan)"),
    start: Optional[str] = Query(None, description="ISO8601, optional"),
    end: Optional[str]   = Query(None, description="ISO8601, optional"),
    adjustment: str = Query("split", description="raw or split"),
    sort: str = Query("asc", description="asc or desc"),
):
    if not start:
        lookback_days = 14 if (timeframe.endswith("Min") or timeframe.endswith("Hour")) else 120
        start = iso(datetime.now(tz=timezone.utc) - timedelta(days=lookback_days))
    params = {"timeframe": timeframe, "limit": str(limit), "feed": feed, "start": start, "adjustment": adjustment, "sort": sort}
    if end: params["end"] = end
    url = f"{data_base()}/stocks/{symbol.upper()}/bars"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=alpaca_headers(), params=params)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {e!s}")
    if r.status_code == 403: raise HTTPException(403, r.text or "Forbidden")
    if r.status_code >= 400: raise HTTPException(r.status_code, r.text or f"Alpaca error {r.status_code}")
    try: data = r.json()
    except ValueError: raise HTTPException(502, f"Non-JSON from Alpaca: {r.text[:500]}")
    bars = data.get("bars") or []
    slim = [{"t": b.get("t"), "o": b.get("o"), "h": b.get("h"), "l": b.get("l"), "c": b.get("c"), "v": b.get("v")} for b in bars]
    return {"symbol": symbol.upper(), "timeframe": timeframe, "count": len(slim), "start_used": start, "feed": feed, "bars": slim}

@router.get("/quotes")
async def quotes(symbol: str, feed: str = Query("iex", description="iex (free) or sip (requires plan)")):
    url = f"{data_base()}/stocks/{symbol.upper()}/snapshot"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=alpaca_headers(), params={"feed": feed})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {e!s}")
    if r.status_code == 403: raise HTTPException(403, r.text or "Forbidden")
    if r.status_code >= 400: raise HTTPException(r.status_code, r.text or f"Alpaca error {r.status_code}")
    try: data = r.json()
    except ValueError: raise HTTPException(502, f"Non-JSON from Alpaca: {r.text[:500]}")
    q = (data or {}).get("latestQuote") or {}; t = (data or {}).get("latestTrade") or {}; d = (data or {}).get("dailyBar") or {}
    bid = q.get("bp"); ask = q.get("ap")
    spread = (ask - bid) if (isinstance(ask, (int, float)) and isinstance(bid, (int, float))) else None
    return {
        "symbol": symbol.upper(), "feed": feed,
        "quote": {"bid": bid, "bidSize": q.get("bs"), "ask": ask, "askSize": q.get("as"), "time": q.get("t"), "spread": spread},
        "lastTrade": {"price": t.get("p"), "size": t.get("s"), "time": t.get("t")},
        "day": {"open": d.get("o"), "high": d.get("h"), "low": d.get("l"), "close": d.get("c"), "volume": d.get("v"),
                "range": [d.get("l"), d.get("h")] if d.get("l") is not None and d.get("h") is not None else None},
    }

# ---- Market Data: Crypto (XRP/USD, etc.) ----
@router.get("/crypto/snapshot")
async def crypto_snapshot(symbol: str, loc: str = "us"):
    sym = symbol.upper()
    url = f"{data_root()}/v1beta3/crypto/{loc}/snapshots"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=alpaca_headers(), params={"symbols": sym})
            r.raise_for_status()
            data = r.json() or {}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Crypto snapshot error: {e!s}")

    snap = ((data.get("snapshots") or {}).get(sym)) or {}
    q = snap.get("latestQuote") or {}
    t = snap.get("latestTrade") or {}
    d = snap.get("dailyBar") or {}
    bid = q.get("bp"); ask = q.get("ap")
    spread = (ask - bid) if (isinstance(ask, (int, float)) and isinstance(bid, (int, float))) else None
    return {
        "symbol": sym,
        "quote": {"bid": bid, "bidSize": q.get("bs"), "ask": ask, "askSize": q.get("as"), "time": q.get("t"), "spread": spread},
        "lastTrade": {"price": t.get("p"), "size": t.get("s"), "time": t.get("t")},
        "day": {"open": d.get("o"), "high": d.get("h"), "low": d.get("l"), "close": d.get("c"), "volume": d.get("v"),
                "range": [d.get("l"), d.get("h")] if d.get("l") is not None and d.get("h") is not None else None},
    }

@router.get("/crypto/bars")
async def crypto_bars(
    symbol: str,
    timeframe: str = Query("1Min", description="e.g., 1Min..59Min, 1Hour..23Hour, 1Day"),
    limit: int = Query(120, ge=1, le=1000),
    loc: str = "us",
    start: Optional[str] = Query(None, description="ISO8601"),
    end: Optional[str]   = Query(None, description="ISO8601"),
    sort: str = Query("asc", description="asc or desc"),
):
    if not start:
        # Look back sensible default for minute bars
        lookback = 2 if timeframe.endswith("Day") else 1
        start = iso(datetime.now(tz=timezone.utc) - timedelta(days=lookback))
    params = {"symbols": symbol.upper(), "timeframe": timeframe, "limit": str(limit), "start": start, "sort": sort}
    if end: params["end"] = end
    url = f"{data_root()}/v1beta3/crypto/{loc}/bars"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=alpaca_headers(), params=params)
            r.raise_for_status()
            data = r.json() or {}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Crypto bars error: {e!s}")

    sym = symbol.upper()
    raw = (data.get("bars") or {})
    seq = raw.get(sym) if isinstance(raw, dict) else raw
    seq = seq or []
    slim = [{"t": b.get("t"), "o": b.get("o"), "h": b.get("h"), "l": b.get("l"), "c": b.get("c"), "v": b.get("v")} for b in seq]
    return {"symbol": sym, "timeframe": timeframe, "count": len(slim), "start_used": start, "bars": slim}

# ---- Orders / Sync / Positions ----
@router.get("/orders")
async def orders(status: Literal["open","closed","all"] = "open",
                 limit: int = Query(50, ge=1, le=500),
                 direction: Literal["asc","desc"] = "desc"):
    params = {"status": status, "limit": str(limit), "direction": direction}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{trading_base()}/orders", headers=alpaca_headers(), params=params)
            r.raise_for_status(); return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Orders error: {e!s}")

@router.post("/orders/sync")
async def orders_sync():
    con = _db()
    s = _get_active_session(con)
    if not s:
        con.close()
        return {"ok": True, "updated": 0, "reason": "no active session"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            ro = await client.get(f"{trading_base()}/orders", headers=alpaca_headers(), params={"status": "open", "limit": "200", "direction": "desc"})
            rc = await client.get(f"{trading_base()}/orders", headers=alpaca_headers(), params={"status": "closed", "limit": "200", "direction": "desc"})
            ro.raise_for_status(); rc.raise_for_status()
            open_orders = ro.json() or []
            closed_orders = rc.json() or []
    except httpx.HTTPError as e:
        con.close()
        raise HTTPException(status_code=502, detail=f"Sync error: {e!s}")

    by_id: Dict[str, Dict[str, Any]] = {o.get("id"): o for o in (open_orders + closed_orders) if o.get("id")}
    cur = con.execute("""SELECT id, order_id FROM session_reservations WHERE session_id=? AND status='open'""", (s["id"],))
    open_res = cur.fetchall()
    updated = 0
    for _, oid in open_res:
        o = by_id.get(oid)
        if not o:
            _release_by_order(con, oid); updated += 1; continue
        st = (o.get("status") or "").lower()
        filled_qty = o.get("filled_qty"); avg_fill_price = o.get("filled_avg_price")
        if st in ("canceled", "expired", "rejected"):
            _release_by_order(con, oid); updated += 1
        elif st in ("filled", "partially_filled"):
            _spend_by_order(con, oid, filled_qty, avg_fill_price); updated += 1
    con.close()
    return {"ok": True, "updated": updated}

@router.get("/positions")
async def positions():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{trading_base()}/positions", headers=alpaca_headers())
            if r.status_code == 404: return []
            r.raise_for_status(); return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Positions error: {e!s}")

@router.post("/positions/close_all")
async def positions_close_all(cancel_orders: bool = True):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if cancel_orders:
                _ = await client.delete(f"{trading_base()}/orders", headers=alpaca_headers())
            r = await client.delete(f"{trading_base()}/positions", headers=alpaca_headers())
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail=r.text or "Close all failed")
            raw = None
            try: raw = r.json()
            except Exception: raw = None
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Close all error: {e!s}")
    try: log_entry("positions_close_all", payload=json.dumps(raw) if raw is not None else None)
    except Exception: pass
    return {"ok": True, "result": raw}

@router.get("/positions/summary")
async def positions_summary():
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            a = await client.get(f"{trading_base()}/account", headers=alpaca_headers()); a.raise_for_status(); account = a.json()
            p = await client.get(f"{trading_base()}/positions", headers=alpaca_headers())
            positions: List[Dict[str, Any]] = []
            if p.status_code != 404:
                p.raise_for_status(); positions = p.json() or []
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Summary error: {e!s}")
    total_mv = sum(f(pos.get("market_value")) for pos in positions)
    total_cb = 0.0
    for pos in positions:
        cb = pos.get("cost_basis")
        total_cb += f(cb) if cb is not None else f(pos.get("avg_entry_price")) * f(pos.get("qty"))
    unreal_pl = sum(f(pos.get("unrealized_pl")) for pos in positions)
    unreal_plpc = (unreal_pl / total_cb) if total_cb > 0 else None
    day_pl = sum(f(pos.get("unrealized_intraday_pl")) for pos in positions)
    prior_mv = sum(f(pos.get("lastday_price")) * f(pos.get("qty")) for pos in positions)
    day_plpc = (day_pl / prior_mv) if prior_mv > 0 else None
    con = _db(); sess = _session_summary(con); con.close()
    summary = {
        "cash": f(account.get("cash")), "equity": f(account.get("equity")),
        "portfolio_value": f(account.get("portfolio_value")), "buying_power": f(account.get("buying_power")),
        "positions_count": len(positions), "market_value": total_mv, "cost_basis": total_cb,
        "unrealized_pl": unreal_pl, "unrealized_plpc": unreal_plpc, "day_pl": day_pl, "day_plpc": day_plpc,
        "session": sess
    }
    return {"summary": summary, "positions": positions, "account": account}

# ---- Order placement / cancel ----
@router.post("/order")
async def order(
    symbol: str,
    qty: Optional[float] = None,                        # allow fractional
    side: Literal["buy","sell"] = "buy",
    type: Literal["market","limit","stop","stop_limit"] = "market",
    time_in_force: Literal["day","gtc","opg","ioc","fok","gtc+"] = "day",
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    extended_hours: bool = False,
    notional: Optional[float] = Query(None, description="For fractional/crypto: dollar amount to trade"),
    max_risk_pct: Optional[float] = Query(None, description="0.01 = 1% of equity cap"),
    note: Optional[str] = None,
    feed: str = "iex",
    session_enforce: bool = True
):
    # Extended-hours guard: Alpaca requires LIMIT + DAY (stocks only)
    if extended_hours:
        if "/" in symbol.upper():
            raise HTTPException(400, json.dumps({"error":"extended_hours_not_applicable_for_crypto"}))
        if type != "limit" or time_in_force != "day":
            raise HTTPException(
                400,
                json.dumps({"error":"extended_hours_requires_limit_day",
                            "message":"Extended hours require type=limit and time_in_force=day"})
            )
        if not limit_price or limit_price <= 0:
            raise HTTPException(400, json.dumps({"error":"extended_hours_limit_price_required"}))

    # Validate qty/notional presence
    if (qty is None or qty <= 0) and (notional is None or notional <= 0):
        raise HTTPException(400, json.dumps({"error":"qty_or_notional_required"}))

    # Estimate price for budget/risk checks
    est_price: Optional[float] = None
    if type in ("limit","stop_limit") and (limit_price is not None and limit_price > 0):
        est_price = float(limit_price)
    else:
        try: est_price = await latest_price(symbol, feed=feed)
        except Exception: est_price = None

    # Risk cap by equity (for buys)
    if side == "buy" and (max_risk_pct is not None and max_risk_pct > 0):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                ar = await client.get(f"{trading_base()}/account", headers=alpaca_headers())
                ar.raise_for_status(); equity = f(ar.json().get("equity"))
        except Exception:
            equity = 0.0
        if equity:
            if notional and notional > 0:
                allowed = equity * float(max_risk_pct)
                if notional > allowed:
                    raise HTTPException(400, json.dumps({"error":"risk_limit","equity":equity,"allowed_dollars":allowed}))
            elif est_price and qty:
                allowed_dollars = equity * float(max_risk_pct)
                allowed_qty = int(max(0, allowed_dollars // est_price))
                if qty > allowed_qty and allowed_qty >= 0:
                    raise HTTPException(400, json.dumps({"error":"risk_limit","equity":equity,"est_price":est_price,"allowed_dollars":allowed_dollars,"allowed_qty":allowed_qty}))

    # Session budget enforcement (buys)
    con = _db(); sess = _get_active_session(con)
    if session_enforce and sess and sess["status"] == "active" and side == "buy":
        summary = _session_summary(con)
        if not summary or summary["status"] != "active":
            con.close(); raise HTTPException(400, json.dumps({"error":"session_inactive"}))
        remaining = f(summary["remaining"])
        ep = est_price if est_price else f(limit_price)
        # Cost estimation
        if notional and notional > 0:
            est_cost = float(notional)
            est_qty  = (est_cost / ep) if (ep and ep > 0) else None
        else:
            if not ep or ep <= 0 or not qty:
                con.close(); raise HTTPException(400, json.dumps({"error":"no_price_estimate"}))
            est_cost = ep * float(qty)
            est_qty  = float(qty)
        if est_cost > remaining:
            allowed_qty = None
            if ep and ep > 0 and notional is None:
                allowed_qty = int(max(0, floor(remaining / ep)))
            con.close(); raise HTTPException(400, json.dumps({
                "error":"session_budget","remaining":remaining,"est_price":ep,
                "allowed_qty":allowed_qty, "allowed_dollars":remaining
            }))
        # Per-symbol throttle
        cur = con.execute("""SELECT max_dollars, max_shares FROM session_symbol_limits
                             WHERE session_id=? AND symbol=?""", (sess["id"], symbol.upper()))
        row = cur.fetchone()
        if row:
            max_dollars, max_shares = row
            used_dollars = _sum_by(con, sess["id"], symbol.upper(), ("open","spent"), "amount")
            used_shares  = _sum_by(con, sess["id"], symbol.upper(), ("open","spent"), "qty")
            if max_dollars is not None and (used_dollars + est_cost) > float(max_dollars):
                con.close(); raise HTTPException(400, json.dumps({"error":"symbol_limit_dollars","symbol":symbol.upper(),"used_dollars":used_dollars,"max_dollars":float(max_dollars),"est_cost":est_cost}))
            if max_shares is not None and (est_qty is not None) and (used_shares + est_qty) > float(max_shares):
                con.close(); raise HTTPException(400, json.dumps({"error":"symbol_limit_shares","symbol":symbol.upper(),"used_shares":used_shares,"max_shares":float(max_shares),"new_qty":est_qty}))

    # Build order body
    body: Dict[str, Any] = {"symbol": symbol.upper(), "side": side, "type": type,
                            "time_in_force": time_in_force, "extended_hours": extended_hours}
    if limit_price and limit_price > 0: body["limit_price"] = limit_price
    if stop_price and stop_price > 0:   body["stop_price"]  = stop_price
    if qty and qty > 0:                 body["qty"] = qty
    if notional and notional > 0:       body["notional"] = notional

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{trading_base()}/orders", headers=alpaca_headers(), json=body)
            if r.status_code >= 400:
                con.close(); raise HTTPException(status_code=r.status_code, detail=r.text)
            order = r.json()
    except httpx.HTTPError as e:
        con.close(); raise HTTPException(status_code=502, detail=f"Place order error: {e!s}")

    try:
        log_entry("order_submitted", order_id=order.get("id"), symbol=symbol.upper(), side=side,
                  qty=qty, price=limit_price, status=order.get("status"), note=note, payload=json.dumps(order))
    except Exception:
        pass

    if session_enforce and sess and sess["status"] == "active" and side == "buy":
        try:
            ep = est_price if est_price else f(limit_price)
            if notional and notional > 0:
                amt = float(notional)
                qest = (amt / ep) if (ep and ep > 0) else 0.0
            else:
                qest = float(qty or 0.0)
                amt = (ep * qest) if (ep and qest) else 0.0
            _reserve(con, sess["id"], order.get("id"), symbol.upper(), side, ep if ep else 0.0, qest, amt)
        except Exception:
            pass

    con.close()
    return order

@router.post("/order/cancel")
async def cancel_order(order_id: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(f"{trading_base()}/orders/{order_id}", headers=alpaca_headers())
            if r.status_code == 404: raise HTTPException(404, "Order not found")
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Cancel order error: {e!s}")
    try:
        con = _db(); _release_by_order(con, order_id); con.close()
        log_entry("order_cancelled", order_id=order_id)
    except Exception:
        pass
    return {"ok": True, "order_id": order_id}

@router.post("/orders/cancel_all")
async def cancel_all_orders():
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.delete(f"{trading_base()}/orders", headers=alpaca_headers())
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail=r.text or "Cancel all failed")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Cancel all error: {e!s}")
    try:
        con = _db(); con.execute("UPDATE session_reservations SET status='released' WHERE status='open'"); con.commit(); con.close()
        log_entry("orders_cancel_all")
    except Exception:
        pass
    return {"ok": True}

# ---- journal / equity ----
@router.get("/journal/entries")
async def journal_entries(limit: int = Query(200, ge=1, le=2000)):
    return {"entries": list_entries(limit=limit)}

@router.post("/journal/log")
async def journal_log(kind: str = "note", symbol: Optional[str] = None, note: Optional[str] = None):
    log_entry(kind, symbol=symbol, note=note)
    return {"ok": True}

@router.post("/journal/snapshot_equity")
async def journal_snapshot_equity():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{trading_base()}/account", headers=alpaca_headers())
            r.raise_for_status(); acc = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Snapshot equity error: {e!s}")
    try: log_entry("equity", price=f(acc.get("equity")), note="equity snapshot", payload=json.dumps(acc))
    except Exception: pass
    return {"ok": True, "equity": f(acc.get("equity"))}

@router.get("/journal/equity")
async def journal_equity(limit: int = Query(1000, ge=1, le=5000)):
    entries = list_entries_by_kind("equity", limit=limit)
    return {"entries": entries}

# ---------- Universe (asset selection) ----------
PRESETS: Dict[str, List[str]] = {
    "Tech Megacaps": ["AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA"],
    "Popular ETFs":  ["SPY","QQQ","DIA","IWM","ARKK","XLF","XLK","XLE"],
    "Futures ETFs":  ["SPXL","SPXS","TQQQ","SQQQ","UVXY","SVXY"],
    "Crypto Starters": ["BTC/USD","ETH/USD","SOL/USD","XRP/USD","USDT/USD"]
}

@router.get("/universe")
async def universe_list():
    con = _db()
    cur = con.execute("SELECT symbol, COALESCE(note,''), COALESCE(active,1) FROM universe_symbols ORDER BY symbol")
    rows = [{"symbol": r[0], "note": r[1], "active": bool(r[2])} for r in cur.fetchall()]
    con.close()
    return {"symbols": rows}

@router.post("/universe/add")
async def universe_add(symbol: str, note: Optional[str] = None, active: bool = True):
    sym = symbol.upper().strip()
    if not sym: raise HTTPException(400, "symbol required")
    con = _db()
    con.execute("""
        INSERT INTO universe_symbols(symbol, note, active) VALUES(?,?,?)
        ON CONFLICT(symbol) DO UPDATE SET note=excluded.note, active=excluded.active
    """, (sym, note, 1 if active else 0))
    con.commit(); con.close()
    return {"ok": True}

@router.post("/universe/bulk_add")
async def universe_bulk_add(symbols_text: str, replace: bool = False):
    # Accept comma/space/newline separated symbols or pairs
    raw = [s.strip().upper() for s in symbols_text.replace(",", " ").split()]
    syms = sorted(set([s for s in raw if s]))
    con = _db()
    if replace:
        con.execute("DELETE FROM universe_symbols")
    for s in syms:
        con.execute("INSERT OR IGNORE INTO universe_symbols(symbol, active) VALUES(?,1)", (s,))
    con.commit(); con.close()
    return {"ok": True, "count": len(syms)}

@router.post("/universe/delete")
async def universe_delete(symbol: str):
    sym = symbol.upper().strip()
    con = _db()
    con.execute("DELETE FROM universe_symbols WHERE symbol=?", (sym,))
    con.commit(); con.close()
    return {"ok": True}

@router.post("/universe/clear")
async def universe_clear():
    con = _db(); con.execute("DELETE FROM universe_symbols"); con.commit(); con.close()
    return {"ok": True}

@router.post("/universe/set_active")
async def universe_set_active(symbol: str, active: bool = True):
    sym = symbol.upper().strip()
    con = _db()
    con.execute("UPDATE universe_symbols SET active=? WHERE symbol=?", (1 if active else 0, sym))
    con.commit(); con.close()
    return {"ok": True}

@router.get("/universe/presets")
async def universe_presets():
    return {"presets": [{"name": k, "symbols": v} for k, v in PRESETS.items()]}

@router.post("/universe/load_preset")
async def universe_load_preset(name: str, replace: bool = True):
    if name not in PRESETS:
        raise HTTPException(404, "Unknown preset")
    syms = PRESETS[name]
    con = _db()
    if replace:
        con.execute("DELETE FROM universe_symbols")
    for s in syms:
        con.execute("INSERT OR IGNORE INTO universe_symbols(symbol, active) VALUES(?,1)", (s,))
    con.commit(); con.close()
    return {"ok": True, "count": len(syms)}
