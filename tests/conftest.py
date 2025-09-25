# File: backend/tests/conftest.py
from __future__ import annotations

import os
import importlib
import shutil
from pathlib import Path
import pytest

@pytest.fixture(scope="session")
def _test_env(tmp_path_factory: pytest.TempPathFactory):
    """
    Prepare isolated env (LOG_DIR, CONFIG_DIR, AUDIT_LOG_PATH) for tests.
    Must run before importing app.main or any router that reads env at import.
    """
    base = tmp_path_factory.mktemp("orion_tests")
    logs = base / "logs"
    cfg  = base / "config"
    logs.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)

    os.environ["APP_NAME"] = "orion-backend"
    os.environ["LOG_DIR"] = str(logs)
    os.environ["CONFIG_DIR"] = str(cfg)
    os.environ["AUDIT_LOG_PATH"] = str(logs / "audit.jsonl")

    # keep guard off by default
    os.environ["BACKEND_API_KEY"] = ""

    # reasonable defaults for risk
    os.environ["DAILY_LOSS_LIMIT"] = "100.0"
    os.environ["MAX_POSITION_RISK"] = "50.0"
    os.environ["ORDER_THROTTLE_SECONDS"] = "5"
    os.environ["COOLOFF_AFTER_DRAWDOWN"] = "1"
    os.environ["SESSION_ENABLED"] = "1"

    yield {"base": base, "logs": logs, "config": cfg}

    # cleanup
    shutil.rmtree(base, ignore_errors=True)

@pytest.fixture(scope="session")
def test_client(_test_env):
    """
    Import the FastAPI app after env is set, and return a TestClient.
    """
    # Ensure fresh modules (orders.py reads env at import time)
    for mod in list(filter(lambda m: m and m.startswith("app."), list(importlib.sys.modules.keys()))):
        importlib.sys.modules.pop(mod, None)

    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
