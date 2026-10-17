
import os

from fastapi import APIRouter, HTTPException

from app.rag.schemas import RetrieveRequest, RetrieveResponse
from app.rag.mock import mock_retrieve
from app.rag.retrieve import retrieve as real_retrieve, IndexNotBuilt

router = APIRouter(prefix="/rag", tags=["rag"])

USE_MOCK = os.getenv("RAG_MOCK", "0") == "1"
ALLOW_FIXED = os.getenv("RAG_ALLOW_FIXED", "0") == "1"


@router.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "mock" if USE_MOCK else "real",
        "strategy": "structured",
    }


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest):
    if req.strategy == "fixed" and not ALLOW_FIXED:
        raise HTTPException(
            status_code=400,
            detail=(
                "Strategy 'fixed' is evaluation-only (rejected for production: "
                "it can merge unrelated entries). Use 'structured'."
            ),
        )

    if USE_MOCK:
        return mock_retrieve(req)

    try:
        return real_retrieve(req)
    except IndexNotBuilt as e:
        raise HTTPException(status_code=503, detail=str(e))