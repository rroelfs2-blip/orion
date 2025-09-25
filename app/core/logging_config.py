from __future__ import annotations
import logging, os, sys
from pathlib import Path

def setup_logging(app_name: str = "orion-backend", log_level: str = "INFO", log_dir: str = "./logs"):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / f"{app_name}.log"
    fmt = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d [%(process)d] - %(message)s"
    handlers = [logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, encoding="utf-8")]
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO),
                        format=fmt, handlers=handlers, force=True)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logger = logging.getLogger("orion")
    logger.info("Logging initialized (app=%s, dir=%s, level=%s)", app_name, log_dir, log_level)
    return logger
