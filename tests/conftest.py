# File: tests/conftest.py
from __future__ import annotations
import importlib
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient


def _mk_temp_tree(prefix: str = "orion_tests") -> Dict[str, Path]:
    base = Path(tempfile.mkdtemp(prefix=prefix + "_"))
    cfg = base / "config"
    logs = base / "logs"
    cfg.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    return {"base": base, "config": cfg, "logs": logs}


@pytest.fixture(scope="session")
def test_env() -> Dict[str, Path]:
    """Session sandbox so tests never touch real repo paths."""
    tree = _mk_temp_tree("orion_tests")
    try:
        yield tree
    finally:
        shutil.rmtree(tree["base"], ignore_errors=True)


# Back-compat alias for tests that request `_test_env`
@pytest.fixture(scope="session", name="_test_env")
def _test_env_alias(test_env):
    return test_env


@pytest.fixture(scope="function")
def test_client(test_env, monkeypatch):
    """
    Function-scoped client so it can use the function-scoped monkeypatch.
    We patch env/paths before importing the app.
    """
    # Env vars (future-proof if app reads them)
    monkeypatch.setenv("ORION_CONFIG_DIR", str(test_env["config"]))
    monkeypatch.setenv("ORION_LOG_DIR", str(test_env["logs"]))

    # Patch modules that compute paths at import time
    try:
        import app.core.risk as risk
        monkeypatch.setattr(risk, "CONFIG_DIR", test_env["config"], raising=False)
        monkeypatch.setattr(risk, "LOG_DIR", test_env["logs"], raising=False)
        # prime throttle timestamp file if code expects it
        (test_env["logs"] / "last_order_ts.txt").write_text("", encoding="utf-8")
    except Exception:
        pass

    try:
        import app.core.usage as usage
        monkeypatch.setattr(usage, "CONFIG_DIR", test_env["config"], raising=False)
        monkeypatch.setattr(usage, "TOKENS_FILE", test_env["config"] / "tokens.json", raising=False)
    except Exception:
        pass

    # Ensure a fresh import of the app after patching
    for mod in list(importlib.sys.modules.keys()):
        if mod.startswith("app."):
            importlib.sys.modules.pop(mod, None)

    from app.main import app
    client = TestClient(app)
    try:
        yield client
    finally:
        # nothing extra per-test
        pass


@pytest.fixture(scope="function")
def temp_config_dir(monkeypatch):
    """
    Lightweight fixture for tests that only need a temp config/ for usage.py.
    """
    from app.core import usage as usage_mod
    base = Path(tempfile.mkdtemp(prefix="orion_usage_test_"))
    cfg = base
    monkeypatch.setattr(usage_mod, "CONFIG_DIR", cfg, raising=False)
    monkeypatch.setattr(usage_mod, "TOKENS_FILE", cfg / "tokens.json", raising=False)
    try:
        yield str(cfg)
    finally:
        shutil.rmtree(base, ignore_errors=True)
