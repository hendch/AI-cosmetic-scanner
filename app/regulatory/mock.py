"""Mock regulatory agent for the Day-1 end-to-end skeleton.

No LLM: it reads the real corpus and applies only the deterministic rules, so its
statuses and sources are already real. Conditions that need interpretation (several
product types, usage limits, label wording) stay "unknown" until the real agent runs.
"""

from app.common_schemas import Ingredient, ProductInput
from app.regulatory import rules
from app.regulatory.kb import RegulatoryKB, load_kb
from app.regulatory.schemas import AgentRunStats, ProductContext, RegulatoryFinding, RegulatoryResponse


def _finding(ingredient: Ingredient, payload: ProductInput, kb: RegulatoryKB) -> RegulatoryFinding:
    if not ingredient.matched:
        return rules.not_assessed(
            ingredient,
            "Ingredient not recognised as an INCI name; no regulatory evidence retrieved.",
            "recognised INCI name",
        )
    canonical = kb.canonical(ingredient.normalized)
    if canonical is None:
        return rules.apply_ocr_confidence(
            rules.not_assessed(
                ingredient,
                "This ingredient is not covered by the current regulatory corpus.",
                "evidence in regulatory corpus",
            ),
            ingredient,
        )
    rows = kb.entries_for(canonical)
    finding = rules.no_restriction(ingredient) if not rows else rules.baseline_finding(ingredient, payload.product, rows)
    return rules.apply_ocr_confidence(finding, ingredient)


def build_mock_response(payload: ProductInput) -> RegulatoryResponse:
    kb = load_kb()
    return RegulatoryResponse(
        prompt_version="mock",
        product_context=ProductContext(
            category=payload.product.category, exposure_type=payload.product.exposure_type
        ),
        findings=[_finding(i, payload, kb) for i in payload.ingredients],
        warnings=payload.warnings,
        run=AgentRunStats(mode="mock"),
    )
