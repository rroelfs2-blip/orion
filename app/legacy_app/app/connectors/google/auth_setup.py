import os
import json
import pathlib
import logging

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

log = logging.getLogger("stratogen")
logging.basicConfig(level=logging.INFO)

# Default scopes (override with GOOGLE_SCOPES env, comma-separated)
DEFAULT_SCOPES = [
    # Gmail basic + send + modify
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    # Drive file-level access (only files you create/open via the app)
    "https://www.googleapis.com/auth/drive",
    # Basic identity (useful for /gmail/profile, etc.)
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

def _env_scopes():
    raw = os.getenv("GOOGLE_SCOPES")
    if not raw:
        return DEFAULT_SCOPES
    scopes = [s.strip() for s in raw.split(",") if s.strip()]
    return scopes or DEFAULT_SCOPES

def _paths():
    """Resolve credentials/token paths."""
    root = pathlib.Path(os.getenv("STRATOGEN_ROOT", os.getcwd()))
    secrets_dir = pathlib.Path(os.getenv("GOOGLE_SECRETS_DIR", root / "secrets" / "google"))
    secrets_dir.mkdir(parents=True, exist_ok=True)

    creds_file = pathlib.Path(os.getenv("GOOGLE_CREDENTIALS_FILE", secrets_dir / "credentials.json"))
    token_file = pathlib.Path(os.getenv("GOOGLE_TOKEN_FILE", secrets_dir / "token.json"))
    return root, secrets_dir, creds_file, token_file

def obtain_credentials():
    _, secrets_dir, creds_file, token_file = _paths()
    scopes = _env_scopes()

    if not creds_file.exists():
        raise FileNotFoundError(
            f"Google OAuth client file not found: {creds_file}\n"
            f"Place your OAuth client JSON at: {creds_file}"
        )

    log.info("Using credentials: %s", creds_file)
    log.info("Will write token to: %s", token_file)
    log.info("Scopes: %s", scopes)

    # Launch local server flow; fall back to console if needed (e.g., headless)
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), scopes=scopes)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    except Exception as e:
        log.warning("Local server auth failed (%s). Falling back to console flow…", e)
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), scopes=scopes)
        creds = flow.run_console()

    token_file.write_text(creds.to_json(), encoding="utf-8")
    log.info("Saved token: %s", token_file)
    return creds

def main():
    creds = obtain_credentials()
    # Confirm shape for sanity
    data = json.loads(creds.to_json())
    who = data.get("id_token") or "(no id_token in this scope set)"
    print("OK: token generated.")
    print("Token file:", _paths()[3])
    print("Has refresh_token:", bool(data.get("refresh_token")))
    print("ID token present:", isinstance(who, str))

if __name__ == "__main__":
    main()

