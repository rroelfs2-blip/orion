import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SECRETS_DIR = os.environ.get("GOOGLE_SECRETS_DIR", os.path.join(os.getcwd(), "secrets"))
TOKEN_PATH = os.path.join(SECRETS_DIR, "token.json")

def load_credentials() -> Credentials:
    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError("Google token.json not found; re-auth required.")
    # IMPORTANT: do NOT pass scopes here; prevents refresh mismatch
    return Credentials.from_authorized_user_file(TOKEN_PATH)

def get_service(api_name: str, api_version: str):
    creds = load_credentials()
    return build(api_name, api_version, credentials=creds, cache_discovery=False)

# ---- Backward-compatible aliases (for legacy imports) ----
def get_drive_service():
    return get_service("drive", "v3")

def get_gmail_service():
    return get_service("gmail", "v1")
