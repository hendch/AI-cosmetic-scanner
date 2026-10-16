"""POST /regulatory/analyze

REGULATORY_MODE selects the implementation:
- "live": real agent (retrieval + LLM + validation). Default when HF_TOKEN or LLM_API_KEY is set.
- "mock": deterministic rules only, no LLM. Default otherwise, and used by the tests.
"""

import os

from fastapi import APIRouter

from app.common_schemas import ProductInput
from app.regulatory import llm  # noqa: F401  loads .env, so REGULATORY_MODE and HF_TOKEN from .env reach _mode()
from app.regulatory.mock import build_mock_response
from app.regulatory.schemas import RegulatoryResponse

router = APIRouter(prefix="/regulatory", tags=["regulatory"])


def _mode() -> str:
    default = "live" if (os.environ.get("HF_TOKEN") or os.environ.get("LLM_API_KEY")) else "mock"
    return os.environ.get("REGULATORY_MODE", default)


@router.post("/analyze", response_model=RegulatoryResponse)
def analyze(payload: ProductInput) -> RegulatoryResponse:
    if _mode() == "live":
        from app.regulatory.agent import analyze as live_analyze

        return live_analyze(payload)
    return build_mock_response(payload)
