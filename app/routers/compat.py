# File: backend/app/routers/compat.py
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

# This router catches old '/api/api/alpaca/*' paths and redirects to '/api/alpaca/*'
# NOTE: In app.main we include this router at prefix "" (root).
router = APIRouter(prefix="/api/api/alpaca", tags=["compat"])

@router.get("/clock")
def legacy_clock():
    return RedirectResponse(url="/api/alpaca/clock", status_code=307)

@router.get("/account")
def legacy_account():
    return RedirectResponse(url="/api/alpaca/account", status_code=307)

@router.get("/debug")
def legacy_debug():
    return RedirectResponse(url="/api/alpaca/debug", status_code=307)

@router.get("/asset/{symbol}")
def legacy_asset(symbol: str):
    return RedirectResponse(url=f"/api/alpaca/asset/{symbol}", status_code=307)

@router.post("/assets/validate")
def legacy_validate():
    return RedirectResponse(url="/api/alpaca/assets/validate", status_code=307)
