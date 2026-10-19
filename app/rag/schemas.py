from typing import Literal, Optional
from pydantic import BaseModel, Field

Strategy = Literal["fixed", "structured"]

class RetrieveRequest(BaseModel):
    ingredient: str
    query: str = "regulatory status and restrictions"
    top_k: int = Field(5, ge=1, le=20)
    strategy: Strategy = "structured"
    # Keep only chunks of these kinds ("regulation", "sccs_opinion", "clp"); None = all.
    # Agents share one index: without it, long SCCS opinions can crowd annex entries out of top_k.
    doc_types: Optional[list[str]] = None

class EvidenceItem(BaseModel):
    evidence_id: str
    text: str
    score: float
    source: str
    section: Optional[str] = None
    source_date: Optional[str] = None
    url: Optional[str] = None
    metadata: dict = {}

class RetrieveResponse(BaseModel):
    ingredient: str
    strategy: Strategy
    covered: bool
    results: list[EvidenceItem]