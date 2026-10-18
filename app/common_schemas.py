"""Schemas shared between modules.

ProductInput mirrors the output of the barcode/OCR module (Person 2) so n8n can
pass that payload to the agents unchanged. Move to the team's shared schema file
once it exists.
"""

from typing import Literal

from pydantic import BaseModel, Field

EvidenceConfidence = Literal["high", "medium", "low"]


class Ingredient(BaseModel):
    position: int
    raw: str
    normalized: str
    matched: bool
    confidence: float = Field(ge=0, le=1)
    # Labels almost never give it; when known (e.g. "2% Niacinamide"), the regulatory agent checks limits with it.
    concentration_percent: float | None = Field(default=None, ge=0, le=100)


class Product(BaseModel):
    name: str = ""
    brand: str = ""
    barcode: str = ""
    category: str | None = None
    exposure_type: Literal["leave_on", "rinse_off"] | None = None
    labels: list[str] = []  # Open Beauty Facts labels_tags, e.g. "en:cruelty-free"


class ProductInput(BaseModel):
    source: Literal["barcode", "ocr"] | None = None  # None when nothing produced ingredients
    product: Product
    ingredients: list[Ingredient]
    needs_review: bool = False
    warnings: list[str] = []
