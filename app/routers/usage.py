# File: app/routers/usage.py
from __future__ import annotations
from typing import List, Optional, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.usage import load_usage, save_usage

router = APIRouter(prefix="/usage", tags=["usage"])

class TokensSetBody(BaseModel):
    current_balance: float = Field(ge=0)
    daily_used: List[float] = Field(default_factory=list)
    currency: Optional[str] = Field(default="USD")

@router.get("/tokens")
def tokens_get() -> Dict[str, Any]:
    u = load_usage()
    return {"ok": True, "usage": u.to_dict()}

@router.post("/tokens/set")
def tokens_set(body: TokensSetBody) -> Dict[str, Any]:
    u = save_usage(body.model_dump())
    return {"ok": True, "usage": u.to_dict()}
