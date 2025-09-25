from base64 import urlsafe_b64encode
from email.message import EmailMessage
from fastapi import APIRouter, HTTPException
from google.auth.exceptions import RefreshError
from app.connectors.google.common import get_service

router = APIRouter(prefix="/gmail", tags=["gmail"])

@router.post("/send")
def send(payload: dict):
    to = (payload or {}).get("to")
    subject = (payload or {}).get("subject", "")
    body = (payload or {}).get("body", "")
    html = (payload or {}).get("html")
    if not to:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "to is required"})
    try:
        service = get_service("gmail", "v1")
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        if html:
            msg.set_content(body or "")
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(body or "")
        raw = urlsafe_b64encode(msg.as_bytes()).decode()
        resp = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"ok": True, "id": resp.get("id")}
    except (RefreshError, FileNotFoundError):
        raise HTTPException(status_code=401, detail={"ok": False, "error": "Google token missing/expired. Re-auth required."})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})
