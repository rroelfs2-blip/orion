# File: app/legacy_app/app/main.py
from __future__ import annotations
import importlib
import logging
import os
import pkgutil
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi import APIRouter

SERVICE_NAME = "stratogen"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.2.0")
ROOT_PATH = os.getenv("ROOT_PATH", "").strip()  # e.g., "/api" in production behind Nginx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(
    title="Stratogen API",
    version=SERVICE_VERSION,
    root_path=ROOT_PATH or "",
)

# --- CORS (dev-friendly; tighten in prod) ---
origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "service": SERVICE_NAME, "version": SERVICE_VERSION}

def _include_router(router_module: str, attr_names: List[str] = ["router", "api"]) -> bool:
    """
    Import a module and include the first APIRouter found under known attribute names.
    Returns True on success, False otherwise.
    """
    try:
        mod = importlib.import_module(router_module)
    except Exception as e:
        log.info("Skip %s (import failed): %s", router_module, e)
        return False

    for attr in attr_names:
        r = getattr(mod, attr, None)
        if isinstance(r, APIRouter):
            app.include_router(r)
            log.info("Included router: %s.%s", router_module, attr)
            return True

    # Some files may expose a factory like get_router()
    getr = getattr(mod, "get_router", None)
    if callable(getr):
        try:
            r = getr()
            if isinstance(r, APIRouter):
                app.include_router(r)
                log.info("Included router via get_router(): %s", router_module)
                return True
        except Exception as e:
            log.info("Failed get_router() in %s: %s", router_module, e)
    log.info("No APIRouter found in %s", router_module)
    return False

def _include_all_from_package(pkg_name: str):
    """
    Auto-discover all python modules inside pkg_name and include APIRouters.
    """
    try:
        pkg = importlib.import_module(pkg_name)
    except Exception as e:
        log.warning("Package %s not importable: %s", pkg_name, e)
        return

    if not hasattr(pkg, "__path__"):
        log.warning("Package %s has no __path__", pkg_name)
        return

    count = 0
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.ispkg:
            # Recurse into subpackages
            _include_all_from_package(f"{pkg_name}.{m.name}")
            continue
        mod_name = f"{pkg_name}.{m.name}"
        if m.name.startswith("_"):
            continue
        if _include_router(mod_name):
            count += 1
    log.info("Auto-included %d routers from %s", count, pkg_name)

# First: include any explicitly named routers if desired (harmless if missing)
for explicit in [
    "app.routers.drive",
    "app.routers.gmail",
    "app.routers.orders",
    "app.routers.market",
    "app.routers.actions",
    "app.routers.connectors",
    "app.routers.system",
]:
    _include_router(explicit)

# Then: auto-discover everything under app.routers (catches the rest)
_include_all_from_package("app.routers")

@app.get("/meta/routers")
def meta_routers() -> Dict[str, Any]:
    """
    Introspection endpoint: shows included route paths for quick debugging from UI.
    """
    paths: List[str] = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            paths.append(r.path)
    paths = sorted(set(paths))
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "root_path": ROOT_PATH or "",
        "count": len(paths),
        "paths": paths,
    }
