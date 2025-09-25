# File: app/core/auth.py
from __future__ import annotations

import os
import hmac
import time
import base64
import hashlib
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field
from fastapi import HTTPException, status
from jose import jwt, JWTError


# Defaults (env overridable)
ALGO = os.getenv("JWT_ALGO", "HS256")
TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", "3600"))

def _b64_secret_from_env() -> bytes:
    """
    Load JWT secret from env; if it's prefixed 'base64:', decode the rest.
    Fallback to a low-strength default for dev only.
    """
    raw = os.getenv("JWT_SECRET", "")
    if not raw:
        raw = "dev-only-not-for-production"
    if raw.startswith("base64:"):
        return base64.urlsafe_b64decode(raw.split("base64:", 1)[1].encode("utf-8"))
    return raw.encode("utf-8")

SECRET = _b64_secret_from_env()


class TokenClaims(BaseModel):
    sub: str = Field(..., min_length=1)         # subject (username/service)
    scopes: List[str] = Field(default_factory=list)
    iat: int                                    # issued at (unix ts)
    exp: int                                    # expiry (unix ts)
    aud: Optional[str] = None                   # audience (optional)
    iss: Optional[str] = "orion-backend"        # issuer

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def sign_token(subject: str, scopes: Optional[List[str]] = None, ttl: Optional[int] = None,
               audience: Optional[str] = None) -> str:
    now = int(time.time())
    exp = now + int(TTL_SECONDS if ttl is None else ttl)
    claims = TokenClaims(sub=subject, scopes=scopes or [], iat=now, exp=exp, aud=audience)
    try:
        return jwt.encode(claims.to_dict(), SECRET, algorithm=ALGO)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"jwt_sign_error: {e}")


def verify_token(token: str, required_scopes: Optional[List[str]] = None, audience: Optional[str] = None) -> TokenClaims:
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO], audience=audience, options={"verify_aud": audience is not None})
        claims = TokenClaims(**payload)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"jwt_verify_error: {e}")
    # scope check (all required must be present)
    if required_scopes:
        have = set(claims.scopes or [])
        need = set(required_scopes)
        if not need.issubset(have):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"missing_scopes: {sorted(list(need-have))}")
    return claims


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
