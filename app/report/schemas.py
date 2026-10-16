from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Verdict = Literal["supported", "overstated", "unsupported"]


# ---- input: the draft built by the n8n "Live - Build draft" node ------------------


class DraftSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    evidence_id: str
    kind: str
    excerpt: str


class Draft(BaseModel):
    """Only the parts the validator reads; the rest of the draft is passed through untouched."""

    model_config = ConfigDict(extra="allow")
    ingredients: list[dict] = Field(min_length=1)
    cruelty_free: dict
    sources: list[DraftSource]


class ValidateRequest(BaseModel):
    draft: Draft
    prompt_version: str = "v4"  # active prompt; see prompts/validator


# ---- output: what the model must return ----------------------------------------


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
