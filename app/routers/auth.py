# File: app/routers/auth.py
from __future__ import annotations

import os
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import sign_token, verify_token, constant_time_compare

router = APIRouter(prefix="/auth", tags=["auth"])

# Simple local credentials for dev; for production, swap to proper provider
DEV_USER = os.getenv("AUTH_DEV_USER", "orion")
DEV_PASS = os.getenv("AUTH_DEV_PASS", "orion")
DEFAULT_SCOPES = ["orion:read", "orion:write"]


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    scopes: List[str] = Field(default_factory=lambda: DEFAULT_SCOPES)
    ttl_seconds: int = Field(default=3600, ge=60, le=24*3600)


class TokenResponse(BaseModel):
    ok: bool = True
    token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> Dict[str, Any]:
    # constant-time compare to avoid timing leaks
    if not (constant_time_compare(body.username, DEV_USER) and constant_time_compare(body.password, DEV_PASS)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    token = sign_token(subject=body.username, scopes=body.scopes, ttl=body.ttl_seconds)
    return {"ok": True, "token": token, "token_type": "bearer", "expires_in": body.ttl_seconds}


def _extract_bearer(auth_header: Optional[str]) -> str:
    if not auth_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_authorization")
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_authorization_header")
    return parts[1].strip()


def require_scopes(required: List[str]):
    def dep(authorization: Optional[str] = Header(default=None, alias="Authorization")):
        token = _extract_bearer(authorization)
        claims = verify_token(token, required_scopes=required)
        return claims
    return dep


@router.get("/verify")
def verify(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Dict[str, Any]:
    token = _extract_bearer(authorization)
    claims = verify_token(token)
    return {"ok": True, "claims": claims.model_dump()}
