from typing import Literal

from pydantic import BaseModel

from app.common_schemas import EvidenceConfidence

HazardEndpoint = Literal[
    "carcinogenicity",
    "mutagenicity",
    "reproductive_toxicity",
    "sensitisation",
    "skin_irritation",
    "eye_irritation",
    "other",
]

ConcernLevel = Literal["none_identified", "low", "moderate", "high", "insufficient_evidence"]


class Hazard(BaseModel):
    endpoint: HazardEndpoint
    classification: str  # e.g. "CLP Skin Sens. 1A (H317)"
    source_id: str  # must match a source_id returned by the retrieval endpoint
    quote: str  # retrieved text supporting the classification


class IngredientFinding(BaseModel):
    position: int
    ingredient: str  # normalized INCI name, as received
    matched: bool
    hazards: list[Hazard] = []
    concern_level: ConcernLevel
    risk_interpretation: str  # hazard vs. consumer risk, never a medical claim
    missing_information: list[str] = []
    evidence_confidence: EvidenceConfidence
    sources: list[str] = []


class ToxicologyResponse(BaseModel):
    agent: Literal["toxicology"] = "toxicology"
    prompt_version: str
    findings: list[IngredientFinding]
    warnings: list[str] = []
