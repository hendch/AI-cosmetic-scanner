from fastapi import APIRouter

from app.common_schemas import ProductInput
from app.toxicology.mock import build_mock_response
from app.toxicology.schemas import ToxicologyResponse

router = APIRouter(prefix="/toxicology", tags=["toxicology"])


@router.post("/analyze", response_model=ToxicologyResponse)
def analyze(payload: ProductInput) -> ToxicologyResponse:
    return build_mock_response(payload)
