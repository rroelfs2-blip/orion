
from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/risk/evaluate")
def evaluate_risk():
    daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT", "500"))
    max_position_risk = float(os.getenv("MAX_POSITION_RISK", "100"))
    # Simulate current exposure
    current_loss = 200  # TODO: pull from real source
    position_risk = 75  # TODO: pull from real source

    result = {
        "allowed": current_loss < daily_loss_limit and position_risk < max_position_risk,
        "loss": current_loss,
        "position": position_risk,
        "limits": {
            "daily_loss_limit": daily_loss_limit,
            "max_position_risk": max_position_risk
        }
    }
    return result
