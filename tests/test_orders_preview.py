# File: backend/tests/test_orders_preview.py
from __future__ import annotations

import time

ORDERS_PREVIEW = "/api/orders/preview"
ORDERS_SCHEMA  = "/api/orders/schema"

def test_schema_available(test_client):
    r = test_client.get(ORDERS_SCHEMA)
    assert r.status_code == 200
    data = r.json()
    assert "request" in data and "response" in data

def test_preview_market_warns_without_price(test_client):
    body = {
        "symbol": "EURUSD",
        "side": "buy",
        "qty": 2,
        "order_type": "market"
        # no price_estimate -> should pass with warnings
    }
    r = test_client.post(ORDERS_PREVIEW, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["status"] in ("PASSED_WITH_WARNINGS", "PASSED")

def test_preview_blocked_by_throttle_and_cooloff(test_client, _test_env):
    # Create files (not strictly necessary once force flags are used, but fine to keep)
    logs = _test_env["logs"]
    cfg  = _test_env["config"]
    (logs / "last_order_ts.txt").write_text(str(time.time()), encoding="utf-8")
    (cfg / "cooloff_active.flag").write_text("1", encoding="utf-8")

    body = {
        "symbol": "AAPL",
        "side": "sell",
        "qty": 1,
        "order_type": "limit",
        "limit_price": 5.0,
        "meta": {
            "overrides": {
                "ORDER_THROTTLE_SECONDS": 60,
                "COOLOFF_AFTER_DRAWDOWN": 1,
                "FORCE_THROTTLE_BLOCK": 1,
                "FORCE_COOLOFF_BLOCK": 1,
            }
        }
    }
    r = test_client.post(ORDERS_PREVIEW, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["status"] == "BLOCKED"

def test_preview_blocked_by_max_position_risk(test_client):
    # Force low max risk via overrides
    body = {
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1,
        "order_type": "limit",
        "limit_price": 35.0,  # notional 35
        "meta": {"overrides": {"MAX_POSITION_RISK": 10.0}}
    }
    r = test_client.post(ORDERS_PREVIEW, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["status"] == "BLOCKED"
