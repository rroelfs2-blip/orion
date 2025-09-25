# File: backend/app/routers/logs.py

from fastapi import APIRouter, Query
import os
from pathlib import Path
from typing import List

router = APIRouter()

def _resolve_log_path() -> Path:
    # Prefer env, else backend/logs/stratogen.log
    from pathlib import Path
    default_path = Path(__file__).resolve().parents[2] / "logs" / "stratogen.log"
    return Path(os.getenv("LOG_FILE_PATH", str(default_path)))

def tail_lines(path: Path, limit: int) -> List[str]:
    if not path.exists():
        return [f"[log file missing at {path.as_posix()}]"]
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return [l.rstrip("\n") for l in lines[-limit:]]
    except Exception as e:
        return [f"[log read error: {e}]"]

@router.get("/logs")
def get_logs(limit: int = Query(200, ge=1, le=5000)):
    path = _resolve_log_path()
    return {
        "path": str(path),
        "limit": limit,
        "lines": tail_lines(path, limit),
    }
