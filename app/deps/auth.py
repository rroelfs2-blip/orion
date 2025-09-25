# File: backend/app/deps/auth.py
from __future__ import annotations

from fastapi import Header, HTTPException, status
from app.core.settings import settings

API_HEADER = "X-Backend-Key"

def api_key_guard(x_backend_key: str | None = Header(default=None, alias=API_HEADER)):
    """
    Optional API-key guard: only enforced if BACKEND_API_KEY is non-empty.
    Supply header: X-Backend-Key: <key>
    """
    required = (settings.backend_api_key or "").strip()
    if not required:
        return  # guard disabled
    if not x_backend_key or x_backend_key.strip() != required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
