from fastapi import APIRouter

from app.report.agent import validate_report
from app.report.builder import build_report
from app.report.schemas import Report, ReportRequest, ValidatedReport, ValidateRequest

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/build", response_model=Report)
def build(payload: ReportRequest) -> Report:
    """Merge the agents' outputs into the report, with evidence text and rule checks. No LLM."""
    return build_report(payload)


@router.post("/validate", response_model=ValidatedReport)
def validate(payload: ValidateRequest) -> ValidatedReport:
    """Validator agent: checks each claim against its evidence text and adds the verdict to the report."""
    return validate_report(payload.report, payload.prompt_version)
