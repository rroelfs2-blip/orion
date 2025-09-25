from __future__ import annotations
import os
from pydantic import BaseModel

class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "orion-backend")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    CONFIG_DIR: str = os.getenv("CONFIG_DIR", "./config")
    AUDIT_LOG_PATH: str = os.getenv("AUDIT_LOG_PATH", "./logs/orders_audit.jsonl")
    ORDER_THROTTLE_SECONDS: int = int(os.getenv("ORDER_THROTTLE_SECONDS", "5"))
    ORDERS_PER_MIN_LIMIT: int = int(os.getenv("ORDERS_PER_MIN_LIMIT", "20"))
    MAX_POSITION_RISK: float = float(os.getenv("MAX_POSITION_RISK", "2500"))
    DAILY_LOSS_LIMIT: float = float(os.getenv("DAILY_LOSS_LIMIT", "500"))
    COOLOFF_AFTER_DRAWDOWN: int = int(os.getenv("COOLOFF_AFTER_DRAWDOWN", "0"))
    SESSION_TZ: str = os.getenv("SESSION_TZ", "America/New_York")
    BACKEND_API_KEY: str = os.getenv("BACKEND_API_KEY", "")

settings = Settings()
