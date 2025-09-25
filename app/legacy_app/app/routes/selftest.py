from pathlib import Path
from fastapi import APIRouter
import json, os

router = APIRouter(tags=["self-test"])

def _find_secrets_dir() -> Path:
    # Reuse the same search logic used by connectors
    env_dir = os.getenv("QUANTA_SECRET_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    here = Path(__file__).resolve().parents[2] / "secrets"
    if here.exists():
        return here
    prog = Path(os.environ.get("ProgramData", r"C:\\ProgramData")) / "QuantaBackend" / "secrets"
    return prog

def _load_creds():
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except Exception as e:
        return None, {"libs_error": str(e)}

    sd = _find_secrets_dir()
    tok = sd / "token.json"
    if not tok.exists():
        return None, {"error": "token.json not found", "secrets_dir": str(sd)}
    try:
        creds = Credentials.from_authorized_user_file(str(tok))
        # Refresh if possible
        if getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            creds.refresh(Request())
            # Persist refreshed token
            tok.write_text(creds.to_json())
        info = {
            "secrets_dir": str(sd),
            "scopes": list(getattr(creds, "scopes", []) or []),
            "valid": bool(getattr(creds, "valid", False)),
            "expired": bool(getattr(creds, "expired", False)),
            "has_refresh": bool(getattr(creds, "refresh_token", None)),
        }
        return creds, info
    except Exception as e:
        return None, {"token_parse_error": str(e), "secrets_dir": str(sd)}

@router.get("/self-test")
def self_test():
    result = {"ok": False, "creds": {}, "gmail": {}, "drive": {}}

    creds, cinfo = _load_creds()
    result["creds"] = cinfo
    if not creds:
        return result

    # Try Gmail profile (read-only)
    try:
        from googleapiclient.discovery import build  # type: ignore
        gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
        prof = gmail.users().getProfile(userId="me").execute()
        result["gmail"] = {
            "ok": True,
            "emailAddress": prof.get("emailAddress"),
            "messagesTotal": prof.get("messagesTotal"),
            "threadsTotal": prof.get("threadsTotal"),
        }
    except Exception as e:
        result["gmail"] = {"ok": False, "error": str(e)}

    # Try Drive about + 1-file list (read-only)
    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        about = drive.about().get(fields="user(emailAddress),storageQuota(limit,usage)").execute()
        sample = drive.files().list(pageSize=1, fields="files(id,name)").execute()
        result["drive"] = {
            "ok": True,
            "user": about.get("user", {}),
            "quota": about.get("storageQuota", {}),
            "sample": sample.get("files", []),
        }
    except Exception as e:
        result["drive"] = {"ok": False, "error": str(e)}

    result["ok"] = bool(result.get("gmail", {}).get("ok") and result.get("drive", {}).get("ok"))
    return result
