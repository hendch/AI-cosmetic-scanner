"""Mock toxicology agent for the Day-1 end-to-end skeleton.

The canned findings are illustrative only: quotes are placeholders, not
retrieved text. The input-handling rules (unmatched ingredients, low OCR
confidence) are meant to stay when the real agent replaces the canned data.
"""

from app.common_schemas import Ingredient, ProductInput
from app.toxicology.schemas import Hazard, IngredientFinding, ToxicologyResponse

OCR_CONFIDENCE_THRESHOLD = 0.8
MOCK_QUOTE = "MOCK - replace with retrieved text"

CANNED_FINDINGS = {
    "methylisothiazolinone": dict(
        hazards=[
            Hazard(
                endpoint="sensitisation",
                classification="CLP Skin Sens. 1A (H317)",
                source_id="clp_test_ingredients",
                quote=MOCK_QUOTE,
            )
        ],
        concern_level="moderate",
        risk_interpretation=(
            "Classified as a skin sensitiser. Whether this matters for this product "
            "depends on concentration and on leave-on vs. rinse-off use."
        ),
        missing_information=["concentration"],
        evidence_confidence="high",
        sources=["clp_test_ingredients", "sccs_methylisothiazolinone_2015"],
    ),
    "phenoxyethanol": dict(
        hazards=[
            Hazard(
                endpoint="eye_irritation",
                classification="CLP Eye Dam. 1 (H318)",
                source_id="clp_test_ingredients",
                quote=MOCK_QUOTE,
            ),
            Hazard(
                endpoint="other",
                classification="CLP Acute Tox. 4 (H302); STOT SE 3 (H335)",
                source_id="clp_test_ingredients",
                quote=MOCK_QUOTE,
            ),
        ],
        concern_level="low",
        risk_interpretation=(
            "A hazard classification exists for the pure substance. Consumer risk "
            "depends on concentration and exposure, which are unknown."
        ),
        missing_information=["concentration"],
        evidence_confidence="high",
        sources=["clp_test_ingredients", "sccs_phenoxyethanol_2016"],
    ),
    "glycerin": dict(
        hazards=[],
        concern_level="none_identified",
        risk_interpretation="No hazard classification or concern identified in the retrieved evidence.",
        missing_information=[],
        evidence_confidence="medium",
        sources=["clp_test_ingredients"],
    ),
}


def _finding(ingredient: Ingredient) -> IngredientFinding:
    base = dict(position=ingredient.position, ingredient=ingredient.normalized, matched=ingredient.matched)

    if not ingredient.matched:
        return IngredientFinding(
            **base,
            concern_level="insufficient_evidence",
            risk_interpretation="Ingredient not recognised as an INCI name; no evidence retrieved.",
            missing_information=["recognised INCI name"],
            evidence_confidence="low",
        )

    canned = CANNED_FINDINGS.get(ingredient.normalized)
    if canned is None:
        finding = IngredientFinding(
            **base,
            concern_level="insufficient_evidence",
            risk_interpretation="No evidence found in the knowledge base for this ingredient.",
            missing_information=["evidence in knowledge base"],
            evidence_confidence="low",
        )
    else:
        finding = IngredientFinding(**base, **canned)

    if ingredient.confidence < OCR_CONFIDENCE_THRESHOLD:
        finding.evidence_confidence = "low"
        finding.missing_information.append("ingredient name from OCR, unverified")

    return finding


def build_mock_response(payload: ProductInput) -> ToxicologyResponse:
    return ToxicologyResponse(
        prompt_version="mock",
        findings=[_finding(i) for i in payload.ingredients],
        warnings=payload.warnings,
    )
