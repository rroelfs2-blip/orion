# File: app/main.py
from __future__ import annotations

import os
import logging
from importlib import import_module
from typing import Optional, Tuple, List

from fastapi import FastAPI
from fastapi.routing import APIRouter

APP_NAME = os.getenv("APP_NAME", "orion-backend")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0-dev")

# Logging bootstrap
LOG_DIR = os.getenv("ORION_LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_DIR = os.path.abspath(LOG_DIR)
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("orion")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(os.path.join(LOG_DIR, "server.log"), encoding="utf-8")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s:%(lineno)d [%(process)d] - %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

logger.info("Starting %s %s", APP_NAME, APP_VERSION)

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    contact={"name": "Orion", "url": "http://localhost"},
)

def try_import_router(module_path: str) -> Optional[APIRouter]:
    try:
        mod = import_module(module_path)
        router = getattr(mod, "router", None)
        if isinstance(router, APIRouter):
            return router
        logger.warning("Module %s has no 'router'", module_path)
        return None
    except Exception as e:
        logger.warning("Router import failed: %s (%s)", module_path, e)
        return None

def mount(module_path: str, prefix: str = "/api") -> Optional[Tuple[str, str]]:
    r = try_import_router(module_path)
    if r:
        # If router already has a prefix (like /usage), leave it; just mount under API root
        app.include_router(r, prefix=prefix)
        logger.info("Mounted router %s at prefix '%s'", module_path, prefix)
        return (module_path, prefix)
    return None

mounted: List[Tuple[str, str]] = []

# Core routers
for m in (
    "app.routers.alpaca",
    "app.routers.orders",
    "app.routers.risk",
    "app.routers.logs",
    "app.routers.system",
    "app.routers.drive",
    "app.routers.debug",
    "app.routers.pnl",
    "app.routers.usage",   # <-- usage (tokens) we just stabilized
    "app.routers.auth",    # <-- NEW auth
):
    res = mount(m, prefix="/api")
    if res:
        mounted.append(res)

# Optional routers (best-effort)
for m in ("app.routers.gmail", "app.routers.chat", "app.routers.oanda", "app.routers.compat"):
    res = mount(m, prefix="/api" if m != "app.routers.compat" else "")
    if res:
        mounted.append(res)

@app.get("/")
def root():
    return {"ok": True, "app": APP_NAME, "mounted": [f"{m} {p}" for (m, p) in mounted]}

@app.get("/healthz")
def health():
    return {"ok": True, "app": APP_NAME, "mounted": [f"{m} {p}" for (m, p) in mounted]}
