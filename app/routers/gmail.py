# File: backend/app/routers/gmail.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os, json, base64, requests
from pathlib import Path
from datetime import datetime

router = APIRouter()

# -------- ENV / Paths --------
OUTBOX_PATH = Path(os.getenv("GMAIL_OUTBOX_PATH", "outbox_gmail.jsonl"))
GMAIL_API_TOKEN = os.getenv("GMAIL_API_TOKEN")  # OAuth bearer
GMAIL_RELAY_BASE = (os.getenv("GMAIL_RELAY_BASE") or "").rstrip("/")
GMAIL_SEND_ENDPOINT = os.getenv("GMAIL_SEND_ENDPOINT", "").strip()  # legacy single-endpoint option
DEFAULT_NOTIFY_TO = os.getenv("DEFAULT_NOTIFY_TO")

def persist_outbox(record: dict):
    OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def _auth_headers():
    if not GMAIL_API_TOKEN:
        raise HTTPException(status_code=503, detail="gmail token missing; set GMAIL_API_TOKEN")
    return {"Authorization": f"Bearer {GMAIL_API_TOKEN}", "Content-Type": "application/json"}

def _relay_url(path: str) -> str:
    if not GMAIL_RELAY_BASE and not GMAIL_SEND_ENDPOINT:
        # No relay configured; we will queue locally
        return ""
    if GMAIL_SEND_ENDPOINT and path == "/send":
        return GMAIL_SEND_ENDPOINT
    if not GMAIL_RELAY_BASE:
        raise HTTPException(status_code=503, detail="GMAIL_RELAY_BASE not configured for this endpoint")
    return f"{GMAIL_RELAY_BASE}{path}"

# -------- Models --------
class GmailMessage(BaseModel):
    to: Optional[EmailStr] = None
    subject: str
    body: str
    from_addr: Optional[EmailStr] = None

class GmailAttachment(BaseModel):
    filename: str
    mime_type: str
    data_base64: str  # base64 of file content

class GmailSendWithAttachment(BaseModel):
    to: Optional[EmailStr] = None
    subject: str
    body: str
    attachments: List[GmailAttachment] = []
    from_addr: Optional[EmailStr] = None

class GmailDraft(BaseModel):
    to: Optional[EmailStr] = None
    subject: str
    body: str
    from_addr: Optional[EmailStr] = None

class GmailLabel(BaseModel):
    name: str

# -------- Send (simple text) --------
@router.post("/gmail/send")
def send_email(message: GmailMessage):
    payload = {
        "to": message.to or DEFAULT_NOTIFY_TO,
        "subject": message.subject,
        "body": message.body,
        "from": message.from_addr or "no-reply@stratogen.local",
        "sent_at": datetime.utcnow().isoformat() + "Z",
    }

    # Local queue if no relay configured
    url = _relay_url("/send")
    if not url:
        persist_outbox({"status": "queued_local", **payload})
        return {"status": "queued_local", "outbox": str(OUTBOX_PATH), "message": payload}

    try:
        r = requests.post(url, headers=_auth_headers(), json=payload, timeout=20)
        if not r.ok:
            persist_outbox({"status": "relay_error", "http": r.status_code, "text": r.text, **payload})
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return {"status": "sent", "provider_response": r.json()}
    except HTTPException:
        raise
    except Exception as e:
        persist_outbox({"status": "queue_on_error", "error": str(e), **payload})
        raise HTTPException(status_code=502, detail=f"gmail relay error: {e}")

# -------- Send with attachments --------
@router.post("/gmail/sendAttachment")
def send_with_attachment(req: GmailSendWithAttachment):
    # Validate base64 early
    for a in req.attachments:
        try:
            base64.b64decode(a.data_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Attachment {a.filename} is not valid base64")

    payload = {
        "to": req.to or DEFAULT_NOTIFY_TO,
        "subject": req.subject,
        "body": req.body,
        "attachments": [a.dict() for a in req.attachments],
        "from": req.from_addr or "no-reply@stratogen.local",
        "sent_at": datetime.utcnow().isoformat() + "Z",
    }

    url = _relay_url("/sendAttachment")
    if not url:
        persist_outbox({"status": "queued_local", **payload})
        return {"status": "queued_local", "outbox": str(OUTBOX_PATH), "message": payload}

    try:
        r = requests.post(url, headers=_auth_headers(), json=payload, timeout=30)
        if not r.ok:
            persist_outbox({"status": "relay_error", "http": r.status_code, "text": r.text, **payload})
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return {"status": "sent", "provider_response": r.json()}
    except HTTPException:
        raise
    except Exception as e:
        persist_outbox({"status": "queue_on_error", "error": str(e), **payload})
        raise HTTPException(status_code=502, detail=f"gmail relay error: {e}")

# -------- Labels --------
@router.get("/gmail/labels")
def list_labels():
    url = _relay_url("/labels")
    if not url:
        return {"status": "unconfigured", "labels": []}
    r = requests.get(url, headers=_auth_headers(), timeout=15)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

@router.post("/gmail/labels")
def create_label(label: GmailLabel):
    url = _relay_url("/labels")
    if not url:
        raise HTTPException(status_code=503, detail="Relay not configured for label create")
    r = requests.post(url, headers=_auth_headers(), json=label.dict(), timeout=15)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

# -------- Search / Threads / Messages --------
@router.get("/gmail/search")
def search(q: str):
    url = _relay_url("/search")
    if not url:
        return {"status": "unconfigured", "results": []}
    r = requests.get(url, headers=_auth_headers(), params={"q": q}, timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

@router.get("/gmail/threads")
def list_threads(q: str = ""):
    url = _relay_url("/threads")
    if not url:
        return {"status": "unconfigured", "threads": []}
    r = requests.get(url, headers=_auth_headers(), params={"q": q}, timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

@router.get("/gmail/messages/{msg_id}")
def get_message(msg_id: str):
    url = _relay_url(f"/messages/{msg_id}")
    if not url:
        return {"status": "unconfigured", "message": None}
    r = requests.get(url, headers=_auth_headers(), timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

# -------- Drafts --------
@router.post("/gmail/drafts")
def create_draft(d: GmailDraft):
    url = _relay_url("/drafts")
    if not url:
        persist_outbox({"status": "draft_local", **d.dict()})
        return {"status": "draft_local", "outbox": str(OUTBOX_PATH), "draft": d.dict()}
    r = requests.post(url, headers=_auth_headers(), json=d.dict(), timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

@router.post("/gmail/drafts/send")
def send_draft(draft_id: str):
    url = _relay_url("/drafts/send")
    if not url:
        raise HTTPException(status_code=503, detail="Relay not configured for draft send")
    r = requests.post(url, headers=_auth_headers(), json={"draft_id": draft_id}, timeout=20)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
