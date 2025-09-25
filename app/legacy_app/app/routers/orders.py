
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import requests

router = APIRouter()

class OrderRequest(BaseModel):
    symbol: str
    qty: float
    side: str  # 'buy' or 'sell'

@router.post("/orders/paper")
def place_order(order: OrderRequest):
    # Optional: import and call local risk check logic here
    alpaca_key = os.getenv("ALPACA_KEY_ID")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    if not alpaca_key or not alpaca_secret:
        raise HTTPException(status_code=400, detail="Missing Alpaca credentials")

    url = "https://paper-api.alpaca.markets/v2/orders"
    headers = {
        "APCA-API-KEY-ID": alpaca_key,
        "APCA-API-SECRET-KEY": alpaca_secret,
        "Content-Type": "application/json"
    }
    data = {
        "symbol": order.symbol.upper(),
        "qty": order.qty,
        "side": order.side,
        "type": "market",
        "time_in_force": "gtc"
    }

    response = requests.post(url, json=data, headers=headers)
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=response.json())
    return response.json()
