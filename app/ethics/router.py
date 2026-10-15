from fastapi import APIRouter

from app.common_schemas import ProductInput
from app.ethics.mock import build_mock_response
from app.ethics.schemas import EthicsResponse

router = APIRouter(prefix="/ethics", tags=["ethics"])


@router.post("/analyze", response_model=EthicsResponse)
def analyze(payload: ProductInput) -> EthicsResponse:
    return build_mock_response(payload)
