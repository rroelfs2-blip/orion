
from fastapi import APIRouter, Query
import os

router = APIRouter()

LOG_PATH = os.getenv("LOG_FILE_PATH", "stratogen.log")

@router.get("/logs")
def get_logs(limit: int = Query(100, ge=1, le=1000)):
    if not os.path.exists(LOG_PATH):
        return {"logs": ["[log file missing]"]}
    with open(LOG_PATH, "r") as f:
        lines = f.readlines()
    return {"logs": lines[-limit:]}
