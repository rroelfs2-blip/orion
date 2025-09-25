# File: app/main.py
from __future__ import annotations
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

APP_NAME = "orion-backend"
VERSION = "0.1.0-dev"

log = logging.getLogger("orion")

def _try_import_router(modpath: str):
    try:
        module = __import__(modpath, fromlist=["router"])
        return module.router, None
    except Exception as e:
        return None, e

app = FastAPI(title=APP_NAME, version=VERSION)

# CORS (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _mount(modpath: str, prefix: str = "/api"):
    router, err = _try_import_router(modpath)
    if router is not None:
        app.include_router(router, prefix=prefix)
        log.info("Mounted router %s at prefix '%s'", modpath, prefix)
    else:
        log.warning("Router import failed: %s (%s)", modpath, err)

# Mount core routers
for r in (
    "app.routers.alpaca",
    "app.routers.orders",
    "app.routers.risk",
    "app.routers.logs",
    "app.routers.system",
    "app.routers.pnl",
    "app.routers.usage",  # <-- added
    # optional:
    "app.routers.gmail",
    "app.routers.drive",
    "app.routers.debug",
    "app.routers.chat",
    "app.routers.compat",
):
    _mount(r, "/api")

@app.get("/healthz")
def healthz():
    # Summarize mounts found
    routes = []
    for r in app.routes:
        if hasattr(r, "path") and hasattr(r, "methods"):
            routes.append((sorted(list(r.methods))[0] if r.methods else "", r.path))
    return {"ok": True, "app": APP_NAME, "mounted": f"{len(routes)} routes"}
