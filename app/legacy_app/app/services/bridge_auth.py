# File: backend/app/legacy_app/app/services/bridge_auth.py
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
        # Single source of truth token (lives in OrionBackend\.env)
        self.bridge_token: Optional[str] = os.getenv("BRIDGE_ORION_TOKEN")

        # Inbox auth mode: loopback_open (default) or token_required
        self.inbox_auth_mode: str = os.getenv("BRIDGE_INBOX_AUTH", "loopback_open").strip().lower()
        if self.inbox_auth_mode not in ("loopback_open", "token_required"):
            self.inbox_auth_mode = "loopback_open"

        # Header styles accepted: bearer,x-bridge
        raw = os.getenv("BRIDGE_ACCEPT_HEADERS", "bearer,x-bridge")
        self.accept_headers = tuple(h.strip().lower() for h in raw.split(",") if h.strip())

        # Accept query token (?token=...) if enabled
        self.accept_query: bool = _env_bool("BRIDGE_ACCEPT_QUERY", False)

    def as_health(self) -> Dict[str, Any]:
        return {
            "auth_mode": self.inbox_auth_mode,
            "accept_headers": list(self.accept_headers),
            "accept_query": self.accept_query,
            "has_token": bool(self.bridge_token),
        }

CFG = BridgeAuthConfig()

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"

def _is_loopback(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1")

def _token_from_headers(request: Request) -> Optional[str]:
    # Authorization: Bearer <token>
    auth = request.headers.get("authorization")
    a_tok = None
    if auth and "bearer" in CFG.accept_headers:
        parts = auth.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            a_tok = parts[1]

    # X-Bridge-Token: <token>
    xb = request.headers.get("x-bridge-token")
    x_tok = xb.strip() if (xb and "x-bridge" in CFG.accept_headers) else None

    if a_tok and x_tok and a_tok != x_tok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conflicting tokens in headers")
    return a_tok or x_tok

def _token_from_query(request: Request) -> Optional[str]:
    if not CFG.accept_query:
        return None
    t = request.query_params.get("token")
    return t.strip() if t else None

def extract_any_token(request: Request) -> Optional[str]:
    h = _token_from_headers(request)
    q = _token_from_query(request)
    if h and q and h != q:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conflicting tokens in header/query")
    return h or q

def validate_token(token: Optional[str]) -> None:
    if not CFG.bridge_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Bridge token not configured")
    if not token or token != CFG.bridge_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized (bad bridge token).")

async def require_token(request: Request) -> None:
    token = extract_any_token(request)
    validate_token(token)

async def inbox_gate(request: Request) -> None:
    """
    Rule:
      - If a token is PRESENT → validate it (never fail just because token exists).
      - Else if mode=loopback_open and client is loopback → allow.
      - Else → require token.
    """
    token = extract_any_token(request)
    if token:
        validate_token(token)
        return
    ip = _client_ip(request)
    if CFG.inbox_auth_mode == "loopback_open" and _is_loopback(ip):
        return
    validate_token(token)
