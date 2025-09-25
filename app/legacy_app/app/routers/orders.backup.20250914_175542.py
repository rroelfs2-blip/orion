from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/orders", tags=["orders"])

class PaperOrder(BaseModel):
    symbol: str
    qty: float
    side: str = "buy"       # buy|sell
    type: str = "market"    # market|limit
    time_in_force: str = "day"

@router.post("/paper")
def place_paper(order: PaperOrder):
    # Local setup: orders not wired yet. Prevent accidental live calls.
    raise HTTPException(status_code=501, detail={"ok": False, "error": "Orders disabled in local setup. Configure Alpaca paper keys and enable later."})
