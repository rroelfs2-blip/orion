from fastapi import APIRouter, HTTPException
import os, requests

router = APIRouter()

@router.post("/bridge/ping")
def ping_bridge():
    url = os.getenv("STRATOGEN_BRIDGE_URL", "http://127.0.0.1:8010/api/ping")
    try:
        res = requests.get(url, timeout=2)
        return {"reachable": res.ok, "status": res.status_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))