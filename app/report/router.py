from fastapi import APIRouter, HTTPException

from app.report.agent import ValidatorError, validate_draft
from app.common.llm import LLMError
from app.report.schemas import ValidateRequest, ValidateResponse

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/validate", response_model=ValidateResponse)
def validate(payload: ValidateRequest) -> ValidateResponse:
    """Validator agent: one verdict per claim in the draft, checked against its cited excerpt."""
    try:
        return validate_draft(payload.draft, payload.prompt_version)
    except (ValidatorError, LLMError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
