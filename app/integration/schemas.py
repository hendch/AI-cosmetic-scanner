"""Pydantic v2 models = the contract between n8n and the FastAPI services (schema_version 0.1).

Rule that matters most: n8n REPLACES its state with each service response, so every
service must echo the full request envelope and add its own fields.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["running", "completed", "needs_input", "invalid_input",
                 "setup_required", "needs_review", "unavailable"]


class Input(BaseModel):
    model_config = ConfigDict(extra="allow")
    barcode: Optional[str] = None
    barcode_image_ref: Optional[str] = None
    label_image_ref: Optional[str] = None
    market: Literal["EU"] = "EU"
    assessment_date: str  # YYYY-MM-DD


class Config(BaseModel):
    model_config = ConfigDict(extra="allow")
    live_integrations_ready: bool
    service_base_url: str
    corpus_version: str
    prompt_version: str
    embedding_revision: str


class Envelope(BaseModel):
    """Request body n8n sends to every service, and the base of every response."""
    model_config = ConfigDict(extra="allow")  # echo everything you do not own
    schema_version: Literal["0.1"]
    request_id: str
    status: Status = "running"
    action: Optional[str] = None
    mode: Optional[str] = None
    origin: Optional[str] = None
    config: Optional[Config] = None
    input: Optional[Input] = None
    error: None = None  # a response with an `error` key is treated as a failure by n8n


class Product(BaseModel):
    category: Literal["cosmetic"]
    name: str
    brand: Optional[str] = None


class Ingredient(BaseModel):
    ingredient_id: str
    name: str
    concentration_percent: Optional[float] = None


class EvidenceSource(BaseModel):
    evidence_id: str
    kind: Literal["regulation", "toxicology", "certification"] | str
    ingredient_ids: list[str]
    source_url: str
    source_version: str
    excerpt: str
    retrieved_at: str
    applicability_verified: Literal[True]
    is_synthetic: Literal[False]

    @field_validator("source_url")
    @classmethod
    def https_only(cls, v):
        if not v.startswith("https://"):
            raise ValueError("source_url must be https://")
        return v


class Rule(BaseModel):
    ingredient_id: str
    rule_state: str  # conditional | prohibited | conflicting | ...
    concentration_required: bool
    condition_result: Literal["unknown", "satisfied", "not_satisfied", "not_assessed"]
    evidence_ids: list[str]


class LookupLog(BaseModel):
    ingredient_id: str
    exact_lookup_complete: bool


class EvidencePack(BaseModel):
    corpus_version: str
    as_of: str
    is_synthetic: Literal[False]
    sources: list[EvidenceSource]
    rules: list[Rule]
    lookup_log: list[LookupLog]


# ---- responses -----------------------------------------------------------
class ProductResolveResponse(Envelope):
    product: Product
    ingredients_raw: Optional[str] = None


class OcrInfo(BaseModel):
    needs_confirmation: Literal[False]


class LabelExtractResponse(Envelope):
    ingredients_raw: str = Field(min_length=1)
    ocr: OcrInfo


class NormalizeResponse(Envelope):
    ingredients: list[Ingredient] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [i.ingredient_id for i in self.ingredients]
        if len(ids) != len(set(ids)):
            raise ValueError("ingredient_id values must be unique")
        return self


class EvidenceResponse(Envelope):
    evidence_pack: EvidencePack
    ingredients: list[Ingredient]  # echoed from normalize

    @model_validator(mode="after")
    def provenance(self):
        ids = {i.ingredient_id for i in self.ingredients}
        for s in self.evidence_pack.sources:
            if not set(s.ingredient_ids) <= ids:
                raise ValueError(f"{s.evidence_id}: ingredient_ids not in ingredient list")
        if self.config and self.evidence_pack.corpus_version != self.config.corpus_version:
            raise ValueError("evidence_pack.corpus_version != config.corpus_version")
        if self.input and self.evidence_pack.as_of != self.input.assessment_date:
            raise ValueError("evidence_pack.as_of != input.assessment_date")
        return self


# ---- what the webhook caller gets back ------------------------------------
class PublicResult(BaseModel):
    schema_version: Literal["0.1"]
    request_id: str
    action: Optional[str] = None
    mode: Optional[str] = None
    origin: Optional[str] = None
    status: Status
    report: Optional[dict] = None       # only when status == completed
    result: Optional[dict] = None       # ingest / evaluate output
    next_action: Optional[dict] = None
    error: Optional[dict] = None        # {code, message}
    validation: Optional[dict] = None
