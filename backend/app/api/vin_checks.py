from fastapi import APIRouter

from app.vin_schemas import VinCheckStatusOut
from app.vin_service import vin_check_status

router = APIRouter(prefix="/api/v1/vin-check", tags=["vin-check"])


@router.get("/status", response_model=VinCheckStatusOut)
def get_vin_check_status() -> VinCheckStatusOut:
    return vin_check_status()
