from typing import Literal

from pydantic import BaseModel

from app.common_schemas import EvidenceConfidence

CrueltyFreeStatus = Literal["VERIFIED", "CLAIMED", "CONFLICTING", "NOT_VERIFIED"]
EvidenceType = Literal["certification", "brand_claim", "regulatory", "third_party_report"]


class EthicsEvidence(BaseModel):
    type: EvidenceType
    source: str
    detail: str
    source_id: str


class Certification(BaseModel):
    name: str
    source_id: str


class EthicsResponse(BaseModel):
    agent: Literal["ethics"] = "ethics"
    prompt_version: str
    brand: str
    parent_company: str | None = None
    status: CrueltyFreeStatus
    status_reason: str
    evidence: list[EthicsEvidence] = []
    certifications_checked: list[str] = []
    certifications_found: list[Certification] = []
    conflicts: list[str] = []
    missing_information: list[str] = []
    evidence_confidence: EvidenceConfidence
    warnings: list[str] = []
