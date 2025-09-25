from fastapi import APIRouter
from ..version import VERSION, BUILD_TS

router = APIRouter(tags=["system"])

@router.get("/version")
def version():
    return {"version": VERSION, "build": BUILD_TS}
