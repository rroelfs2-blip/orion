# File: backend/app/routers/drive.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os, json, base64, requests
from pathlib import Path
from datetime import datetime

router = APIRouter()

# -------- ENV / Paths --------
GOOGLE_DRIVE_TOKEN = os.getenv("GOOGLE_DRIVE_TOKEN")
DRIVE_RELAY_BASE = (os.getenv("DRIVE_RELAY_BASE") or "").rstrip("/")
DRIVE_STAGING_DIR = Path(os.getenv("DRIVE_STAGING_DIR", "staging_drive"))

def _auth_headers():
    if not GOOGLE_DRIVE_TOKEN:
        raise HTTPException(status_code=503, detail="drive token missing; set GOOGLE_DRIVE_TOKEN")
    return {"Authorization": f"Bearer {GOOGLE_DRIVE_TOKEN}", "Content-Type": "application/json"}

def _relay_url(path: str) -> str:
    if not DRIVE_RELAY_BASE:
        return ""
    return f"{DRIVE_RELAY_BASE}{path}"

# -------- Models --------
class CreateFolderReq(BaseModel):
    name: str
    parentId: Optional[str] = None

class UploadBase64Req(BaseModel):
    name: str
    data_base64: str
    mime_type: str = "application/octet-stream"
    folderId: Optional[str] = None

# -------- Folders --------
@router.post("/drive/folders")
def create_folder(req: CreateFolderReq):
    url = _relay_url("/folders")
    if not url:
        # local fallback: create a directory under staging
        target = DRIVE_STAGING_DIR / (req.parentId or "") / req.name
        target.mkdir(parents=True, exist_ok=True)
        return {"status": "staged_local", "path": str(target)}
    r = requests.post(url, headers=_auth_headers(), json=req.dict(), timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

# -------- List / Search --------
@router.get("/drive/list")
def list_files(parentId: Optional[str] = None):
    url = _relay_url("/list")
    if not url:
        # local fallback: list staging
        base = DRIVE_STAGING_DIR / (parentId or "")
        base.mkdir(parents=True, exist_ok=True)
        items = []
        for p in base.glob("*"):
            items.append({"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else None})
        return {"status": "staged_local", "items": items}
    r = requests.get(url, headers=_auth_headers(), params={"parentId": parentId} if parentId else {}, timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

@router.get("/drive/search")
def search_files(q: str):
    url = _relay_url("/search")
    if not url:
        # local fallback: simple name contains match
        base = DRIVE_STAGING_DIR
        base.mkdir(parents=True, exist_ok=True)
        matches = []
        for p in base.rglob("*"):
            if q.lower() in p.name.lower():
                matches.append({"name": p.name, "path": str(p), "is_dir": p.is_dir()})
        return {"status": "staged_local", "results": matches}
    r = requests.get(url, headers=_auth_headers(), params={"q": q}, timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

# -------- Upload (base64) --------
@router.post("/drive/uploadBase64")
def upload_base64(req: UploadBase64Req):
    # validate base64
    try:
        content = base64.b64decode(req.data_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="data_base64 is not valid base64")

    url = _relay_url("/uploadBase64")
    if not url:
        # local fallback: write to staging
        DRIVE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
        sub = DRIVE_STAGING_DIR / (req.folderId or "")
        sub.mkdir(parents=True, exist_ok=True)
        target = sub / req.name
        with target.open("wb") as f:
            f.write(content)
        return {"status": "staged_local", "path": str(target), "size": len(content), "mime_type": req.mime_type}

    payload = {
        "name": req.name,
        "data_base64": req.data_base64,
        "mime_type": req.mime_type,
        "folderId": req.folderId,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    r = requests.post(url, headers=_auth_headers(), json=payload, timeout=60)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
