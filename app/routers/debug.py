# File: backend/app/routers/debug.py

from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/debug/env")
def read_env():
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ENABLE_LIVE": os.getenv("ENABLE_LIVE"),
        "ALPACA_KEY": os.getenv("ALPACA_KEY"),
        "ALPACA_SECRET": os.getenv("ALPACA_SECRET"),
        "BRIDGE_ORION_TOKEN": os.getenv("BRIDGE_ORION_TOKEN"),
    }
