# File: backend/app/legacy_app/app/services/auth.py
import os
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")

class BridgeAuthConfig:
    def __init__(self) -> None:
        # Single source of truth token
        self.bridge_token: Optional[str] = os.getenv("BRIDGE_ORION_TOKEN")

        # BRIDGE_INBOX_AUTH: "loopback_open" (default) or "token_required"
        self.inbox_auth_mode: str = os.getenv("BRIDGE_INBOX_AUTH", "loopback_open").strip().lower()
        if self.inbox_auth_mode not in ("loopback_open", "token_required"):
            self.inbox_auth_mode = "loopback_open"

        # Which header styles to accept; comma list: bearer,x-bridge
        raw = os.getenv("BRIDGE_ACCEPT_HEADERS", "bearer,x-bridge")
        self.accept_headers = tuple(h.strip().lower() for h in raw.split(",") if h.strip())

        # Optionally accept query token (?token=...)
        self.accept_query: bool = _env_bool("BRIDGE_ACCEPT_QUERY", False)

    def health_info(self) -> Dict[str, Any]:
        return {
            "auth_mode": self.inbox_auth_mode,
            "accept_headers": list(self.accept_headers),
            "accept_query": self.accept_query,
            "has_token": bool(self.bridge_token),
        }

CFG = BridgeAuthConfig()

def _get_client_ip(request: Request) -> str:
    # trust first X-Forwarded-For if present, else client.host
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"

def _is_loopback(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1")

def _extract_token_from_headers(request: Request) -> Optional[str]:
    # Authorization: Bearer <token>
    auth = request.headers.get("authorization")
    auth_token = None
    if auth and "bearer" in CFG.accept_headers:
        parts = auth.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            auth_token = parts[1]

    # X-Bridge-Token: <token>
    xbridge = request.headers.get("x-bridge-token")
    xb_token = xbridge.strip() if (xbridge and "x-bridge" in CFG.accept_headers) else None

    # If both present and mismatch → reject
    if auth_token and xb_token and auth_token != xb_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conflicting tokens in headers")

    return auth_token or xb_token

def _extract_query_token(request: Request) -> Optional[str]:
    if not CFG.accept_query:
        return None
    tok = request.query_params.get("token")
    return tok.strip() if tok else None

def extract_any_token(request: Request) -> Optional[str]:
    htok = _extract_token_from_headers(request)
    qtok = _extract_query_token(request)
    if htok and qtok and htok != qtok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conflicting tokens in header/query")
    return htok or qtok

def validate_token_value(token: Optional[str]) -> None:
    if not CFG.bridge_token:
        # No configured token → consider it a server misconfig; reject mutations, but allow inbox loopback per mode.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Bridge token not configured")
    if not token or token != CFG.bridge_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized (bad bridge token).")

async def require_token(request: Request) -> None:
    """Dependency for mutation endpoints: require a valid token via allowed styles."""
    token = extract_any_token(request)
    validate_token_value(token)

async def inbox_gate(request: Request) -> None:
    """
    Inbox rule:
      - If a token is PRESENT → validate it (never fail ONLY because a token was sent).
      - Else, if mode == loopback_open and client is loopback → allow.
      - Else, if mode == token_required → require/validate token.
    """
    token = extract_any_token(request)
    if token:
        validate_token_value(token)
        return

    ip = _get_client_ip(request)
    if CFG.inbox_auth_mode == "loopback_open" and _is_loopback(ip):
        return

    # token_required or non-loopback access with loopback_open → require token
    validate_token_value(token)
