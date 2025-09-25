# File: backend/app/logging_config.py
from __future__ import annotations
import os, logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

BASE_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "stratogen.log"

MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(1_000_000)))  # ~1 MB default
BACKUPS   = int(os.getenv("LOG_BACKUPS", "5"))

# root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

# Rotating file handler
fh = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
fh.setLevel(logging.INFO)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

# Avoid duplicate handlers if reloaded
for h in list(logger.handlers):
    logger.removeHandler(h)
logger.addHandler(ch)
logger.addHandler(fh)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
