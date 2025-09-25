# File: tests/test_usage_tokens.py
from __future__ import annotations

def test_tokens_get_default(test_client, temp_config_dir):
    r = test_client.get("/api/usage/tokens")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    u = data["usage"]
    assert u["current_balance"] == 0.0
    assert u["avg_per_day"] == 0.0
    assert u["days"] == 0
    assert isinstance(u["daily_used"], list)

def test_tokens_set_and_get(test_client, temp_config_dir):
    body = {
        "current_balance": 42.5,
        "daily_used": [1.2, 0.9, 2.1, 0.5, 0.0, 1.3, 0.8],
        "currency": "USD",
    }
    r = test_client.post("/api/usage/tokens/set", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    u = data["usage"]
    assert u["current_balance"] == 42.5
    assert u["days"] == 7
    # avg = 1.2+0.9+2.1+0.5+0.0+1.3+0.8 = 6.8 / 7 = 0.971428...
    assert abs(u["avg_per_day"] - (sum(body["daily_used"])/len(body["daily_used"]))) < 1e-9

    # Read back with GET
    r2 = test_client.get("/api/usage/tokens")
    assert r2.status_code == 200
    u2 = r2.json()["usage"]
    assert u2["current_balance"] == 42.5
    assert u2["days"] == 7
