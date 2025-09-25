from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import os, smtplib, ssl
from email.message import EmailMessage

router = APIRouter(prefix="/email", tags=["email"])

class EmailTestPayload(BaseModel):
    to: EmailStr
    subject: str = "Stratogen test"
    body: str = "This is a test from Stratogen."

def send_email_smtp(to_addr: str, subject: str, body: str):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("DEFAULT_NOTIFY_FROM", user)
    tls = (os.getenv("SMTP_TLS", "true").lower() in ("1","true","yes","on"))

    if not all([host, user, pwd, sender]):
        raise RuntimeError("SMTP not configured: set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, DEFAULT_NOTIFY_FROM")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if tls:
            context = ssl.create_default_context()
            smtp.starttls(context=context)
        smtp.login(user, pwd)
        smtp.send_message(msg)

@router.post("/test")
def email_test(payload: EmailTestPayload):
    try:
        send_email_smtp(payload.to, payload.subject, payload.body)
        return {"ok": True, "to": payload.to}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
