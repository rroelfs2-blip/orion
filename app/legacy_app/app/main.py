# File: backend/app/legacy_app/app/main.py
import os, pkgutil, importlib, inspect
from datetime import datetime, timezone
from typing import List
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

SERVICE_NAME = "stratogen"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.2.0")
ROOT_PATH = os.getenv("ROOT_PATH", "").strip()  # e.g., "/api" behind Nginx

# Load .env quietly
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = FastAPI(
    title="Stratogen API",
    version=SERVICE_VERSION,
    root_path=ROOT_PATH or "",
)

# CORS for local UI (React/Streamlit) + same-host
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173", "http://localhost:5173",  # Vite
        "http://127.0.0.1:8501", "http://localhost:8501",  # Streamlit
        "http://127.0.0.1", "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}

@app.get("/version")
def version():
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION, "root_path": ROOT_PATH or ""}

# ---- Auto-mount all routers under app/routers ----
def _mount_all():
    try:
        from . import routers as routers_pkg
    except Exception as e:
        print(f"[routers] package not found: {e}")
        return
    for mod in pkgutil.iter_modules(routers_pkg.__path__, routers_pkg.__name__ + "."):
        try:
            m = importlib.import_module(mod.name)
            mounted = False

            r = getattr(m, "router", None)
            if isinstance(r, APIRouter):
                app.include_router(r)  # DO NOT add extra prefixes; routers define their own
                mounted = True
                print(f"[mount] {mod.name}  prefix='{getattr(r,'prefix','')}' tags={getattr(r,'tags',[])}")

            if not mounted:
                for name, obj in inspect.getmembers(m):
                    if isinstance(obj, APIRouter):
                        app.include_router(obj)
                        print(f"[mount] {mod.name}:{name}  prefix='{getattr(obj,'prefix','')}' tags={getattr(obj,'tags',[])}")
                        mounted = True
            if not mounted:
                print(f"[mount] {mod.name} has no APIRouter")
        except Exception as e:
            print(f"[mount] FAILED {mod.name}: {e}")

_mount_all()

# Introspection (kept handy)
@app.get("/meta/routers")
def meta_routers():
    paths: List[str] = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            paths.append(r.path)
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION, "root_path": ROOT_PATH or "", "count": len(set(paths)), "paths": sorted(set(paths))}
