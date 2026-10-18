"""Report module schemas: the merged report (POST /report/build) and the validator agent (POST /report/validate).

Inputs are the real agent outputs, unchanged: ProductInput (ingestion), RegulatoryResponse,
ToxicologyResponse, EthicsResponse. Every claim in the report points to evidence items with their
text (`sources[].excerpt`), so the validator agent and the app can show what the claim rests on.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common_schemas import EvidenceConfidence, ProductInput
from app.ethics.schemas import EthicsResponse
from app.regulatory.schemas import ComplianceCheck, ConditionCheck, RegulatoryResponse, RegulatoryStatus
from app.toxicology.schemas import ConcernLevel, HazardEndpoint, ToxicologyResponse

Verdict = Literal["supported", "overstated", "unsupported"]
CrueltyFreeStatus = Literal["verified", "claimed", "conflicting", "not_verified", "not_assessed"]
EvidenceKind = Literal["regulation", "coverage_list", "toxicology", "certification", "brand_claim", "third_party", "other"]


# ---- /report/build input ---------------------------------------------------------


class ReportRequest(BaseModel):
    """What n8n has collected at the end of a scan. A missing agent output is allowed:
    that part of the report is marked not assessed and a warning check fails."""

    product_input: ProductInput
    regulatory: RegulatoryResponse | None = None
    toxicology: ToxicologyResponse | None = None
    ethics: EthicsResponse | None = None


# ---- the report ----------------------------------------------------------------------


class SourceRef(BaseModel):
    evidence_id: str  # e.g. "eu_1223_2009_annex_v#57"
    source_id: str  # corpus file, e.g. "eu_1223_2009_annex_v" (corpus/sources.csv)
    kind: EvidenceKind
    excerpt: str  # the text the claim rests on ("" if the agent gave none: a check fails)
    title: str | None = None
    publisher: str | None = None
    date: str | None = None
    url: str | None = None
    in_corpus: bool  # False: the source_id is not registered in corpus/sources.csv


class RegulatoryPart(BaseModel):
    status: RegulatoryStatus
    compliance_check: ComplianceCheck
    entries: list[str] = []  # "V/57"
    conditions: list[ConditionCheck] = []
    explanation: str
    evidence_ids: list[str] = []


class HazardPart(BaseModel):
    endpoint: HazardEndpoint
    label: str  # the classification, e.g. "CLP Skin Sens. 1A (H317)"
    evidence_ids: list[str] = []


class ToxicologyPart(BaseModel):
    concern_level: ConcernLevel
    hazards: list[HazardPart] = []
    explanation: str
    evidence_ids: list[str] = []


class IngredientReport(BaseModel):
    position: int
    ingredient_id: str  # normalized INCI name
    raw: str  # as printed on the label / product database
    matched: bool
    concentration_percent: float | None = None  # null = unknown (labels never give it)
    covered: bool  # at least one cited regulatory or toxicology evidence item with text
    regulatory: RegulatoryPart
    toxicology: ToxicologyPart
    missing_information: list[str] = []
    evidence_confidence: EvidenceConfidence


class CrueltyFree(BaseModel):
    status: CrueltyFreeStatus
    explanation: str
    brand_claim_found: bool
    certifications_found: list[str] = []
    certifications_checked: list[str] = []
    conflicts: list[str] = []
    evidence_ids: list[str] = []
    evidence_confidence: EvidenceConfidence


class Overview(BaseModel):
    total_ingredients: int
    prohibited: int
    restricted: int
    conditions_not_met: int  # restricted ingredients with a condition the product breaks
    conditions_unknown: int  # restricted ingredients whose conditions cannot be checked
    concentration_unknown: int
    hazard_classified: int
    not_assessed: int


class EvidenceCoverage(BaseModel):
    covered: int
    total: int
    percent: int
    definition: str


class ValidationCheck(BaseModel):
    name: str
    severity: Literal["error", "warning"]
    passed: bool
    description: str
    issues: list[str] = []


class Validation(BaseModel):
    passed: bool  # no failed error-level check
    checks: list[ValidationCheck]


class ReportProduct(BaseModel):
    name: str
    brand: str
    barcode: str
    category: str | None = None
    exposure_type: Literal["leave_on", "rinse_off"] | None = None


class Report(BaseModel):
    report_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    input_source: Literal["barcode", "ocr"] | None
    product: ReportProduct
    needs_review: bool  # ingestion was unsure of some ingredient names
    overview: Overview
    ingredients: list[IngredientReport]
    cruelty_free: CrueltyFree
    evidence_coverage: EvidenceCoverage
    sources: list[SourceRef]
    validation: Validation
    prompt_versions: dict[str, str | None]
    warnings: list[str] = []
    limitations: list[str]


# ---- validator agent -------------------------------------------------------------------


class DraftSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    evidence_id: str
    kind: str
    excerpt: str


class Draft(BaseModel):
    """What the validator model reads: the claims and the evidence text they cite."""

    model_config = ConfigDict(extra="allow")
    ingredients: list[dict] = Field(min_length=1)
    cruelty_free: dict
    sources: list[DraftSource]


class Claim(BaseModel):
    agent: Literal["regulatory", "toxicology", "ethics"]
    ingredient_id: str | None = None
    claim: str
    evidence_ids: list[str] = []
    verdict: Verdict
    reason: str = ""

    @field_validator("agent", mode="before")
    @classmethod
    def cruelty_free_is_ethics(cls, v):
        # The draft calls the ethics section "cruelty_free", and the model sometimes uses that name.
        return "ethics" if v == "cruelty_free" else v


class ValidatorOutput(BaseModel):
    valid: bool
    claims: list[Claim] = []  # v1 does not ask for claims
    issues: list[str]
    unsupported_evidence_ids: list[str] = []

    @model_validator(mode="after")
    def valid_from_verdicts(self):
        # The model's own "valid" flag is unreliable (observed: all claims supported, valid=false).
        # With per-claim verdicts, validity is computed from them; v1 has no claims, so its flag stands.
        if self.claims:
            self.valid = all(c.verdict == "supported" for c in self.claims) and not self.unsupported_evidence_ids
        return self


class ValidateResponse(BaseModel):
    prompt_version: str
    model: str
    attempts: int  # 2 means the first answer was not valid JSON for the schema
    result: ValidatorOutput


class ValidateRequest(BaseModel):
    report: Report
    prompt_version: str = "v5"  # active prompt; see prompts/validator


class ValidatedReport(BaseModel):
    """/report/validate answer: the report with the validator's verdict added as a check."""

    status: Literal["completed", "needs_review"]
    report: Report
    validator: ValidateResponse | None = None  # None when the model could not be reached
