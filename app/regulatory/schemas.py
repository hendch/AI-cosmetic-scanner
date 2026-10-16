"""Output schema of the regulatory agent.

Shared field names (ingredient, sources, evidence_confidence, missing_information,
warnings) follow docs/STRUCTURE.md so the report can treat every agent the same way.
"""

from typing import Literal

from pydantic import BaseModel

from app.common_schemas import EvidenceConfidence

# prohibited           Annex II entry for this ingredient
# restricted           Annex III, IV, V or VI entry: allowed only under the listed conditions
# no_restriction_found ingredient is in the corpus scope and no annex entry exists for it
# not_assessed         ingredient not recognised, or outside the corpus scope
RegulatoryStatus = Literal["prohibited", "restricted", "no_restriction_found", "not_assessed"]

# satisfied      product information proves the condition is met
# not_satisfied  product information proves it is not met (e.g. rinse-off only, product is leave-on)
# unknown        the information needed is missing (e.g. concentration not on the label)
# not_applicable the condition does not concern this product
ConditionResult = Literal["satisfied", "not_satisfied", "unknown", "not_applicable"]

ConditionType = Literal[
    "product_type",       # product type or body area (rinse-off, face, oral, ...)
    "max_concentration",  # maximum concentration in the ready-for-use preparation
    "population",         # e.g. not for children under 3
    "usage",              # other limitations (inhalation, purpose, form, purity, ...)
    "labelling",          # warnings or ingredient-list mentions required on the label
]

# compliance_check summarises the conditions:
# not_satisfied if any condition is not_satisfied (or the ingredient is prohibited),
# otherwise unknown if any condition is unknown, otherwise satisfied.
# not_applicable when there is no restriction to check (no_restriction_found / not_assessed).
ComplianceCheck = Literal["satisfied", "not_satisfied", "unknown", "not_applicable"]


class AnnexEntry(BaseModel):
    annex: str  # "II" ... "VI"
    entry: str  # reference number in the annex, e.g. "57" or "12a"
    source_id: str  # corpus file the entry comes from, e.g. "eu_1223_2009_annex_v"


class ConditionCheck(BaseModel):
    entry: str  # which annex entry the condition belongs to, e.g. "V/57"
    type: ConditionType
    requirement: str  # condition text as written in the regulation
    result: ConditionResult
    reason: str


class RegulatoryFinding(BaseModel):
    position: int
    ingredient: str  # normalized INCI name, as received
    matched: bool
    regulatory_status: RegulatoryStatus
    entries: list[AnnexEntry] = []
    conditions: list[ConditionCheck] = []
    compliance_check: ComplianceCheck
    explanation: str  # consumer-facing, never claims safe/unsafe or legal/illegal
    missing_information: list[str] = []
    evidence_confidence: EvidenceConfidence
    sources: list[str] = []


class ProductContext(BaseModel):
    category: str | None = None
    exposure_type: Literal["leave_on", "rinse_off"] | None = None


class AgentRunStats(BaseModel):
    """How the run went: used for the evaluation and for debugging, not shown to consumers."""
    mode: Literal["mock", "live"]
    model: str | None = None
    retrieval_backend: str = "local"
    llm_calls: int = 0
    retries: int = 0
    fallbacks: int = 0  # LLM output still invalid after the retry -> conservative baseline used
    status_disagreements: int = 0  # LLM proposed a different status than the retrieved annex
    overrides: list[str] = []  # safety rules that corrected the LLM output


class RegulatoryResponse(BaseModel):
    agent: Literal["regulatory"] = "regulatory"
    prompt_version: str
    product_context: ProductContext
    findings: list[RegulatoryFinding]
    warnings: list[str] = []
    run: AgentRunStats | None = None
