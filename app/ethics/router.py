from fastapi import APIRouter

from app.common_schemas import ProductInput
from app.ethics.agent import analyze as run_agent
from app.ethics.schemas import EthicsResponse

router = APIRouter(prefix="/ethics", tags=["ethics"])


@router.post("/analyze", response_model=EthicsResponse)
def analyze(payload: ProductInput) -> EthicsResponse:
    return run_agent(payload)
