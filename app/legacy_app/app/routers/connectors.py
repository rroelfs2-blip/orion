import os
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(tags=["connectors"])

def _find_secrets_dir() -> Path:
    # Priority: env override → src/secrets → ProgramData
    env_dir = os.getenv("QUANTA_SECRET_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    here = Path(__file__).resolve().parents[2] / "secrets"
    if here.exists():
        return here
    prog = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "QuantaBackend" / "secrets"
    return prog

def _check_env():
    return {
        "PT_API_KEY": bool(os.getenv("PT_API_KEY")),
        "QUANTA_SECRET_DIR": os.getenv("QUANTA_SECRET_DIR") or None,
    }

def _check_google():
    info = {}
    sd = _find_secrets_dir()
    info["secrets_dir"] = str(sd)
    cred = sd / "credentials.json"
    tok  = sd / "token.json"
    info["credentials_json"] = cred.exists()
    info["token_json"] = tok.exists()

    # Try libs + parse token (no network calls)
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        info["google_libs"] = True
        if tok.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(tok))
                info["token_valid"] = bool(getattr(creds, "valid", False))
                info["token_expired"] = bool(getattr(creds, "expired", False))
                scopes = getattr(creds, "scopes", None)
                info["token_scopes"] = list(scopes) if scopes else []
            except Exception as e:
                info["token_parse_error"] = str(e)
    except Exception as e:
        info["google_libs"] = False
        info["libs_error"] = str(e)

    info["ok"] = bool(info.get("google_libs") and cred.exists() and tok.exists())
    return info

@router.get("/connectors/health")
def connectors_health():
    env = _check_env()
    google = _check_google()
    ok = bool(google.get("ok"))
    return {"ok": ok, "env": env, "google": google}
