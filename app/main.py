from __future__ import annotations
import os
from fastapi import FastAPI
from app.core.settings import settings
from app.core.logging_config import setup_logging

app = FastAPI(title=settings.APP_NAME)

logger = setup_logging(settings.APP_NAME, settings.LOG_LEVEL, settings.LOG_DIR)
logger.info("Starting %s", settings.APP_NAME)

mounted = []
def _try_mount(import_path: str, prefix: str = "/api"):
    try:
        mod = __import__(import_path, fromlist=['router'])
        app.include_router(mod.router, prefix=prefix)
        mounted.append((import_path, prefix))
    except Exception as e:
        logger.warning("Router import failed: %s (%s)", import_path, e)

_try_mount("app.routers.alpaca")
_try_mount("app.routers.orders")
_try_mount("app.routers.risk")
_try_mount("app.routers.logs")
_try_mount("app.routers.system")
_try_mount("app.routers.pnl")
_try_mount("app.routers.debug")
_try_mount("app.routers.compat", prefix="")

@app.get("/healthz")
def healthz():
    return {"ok": True, "app": settings.APP_NAME, "mounted": mounted}
