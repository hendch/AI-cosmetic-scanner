"""Mock cruelty-free agent for the Day-1 end-to-end skeleton.

Status rules:
- VERIFIED: brand found in a curated certification list.
- CLAIMED: cruelty-free label/claim, but no certification found.
- CONFLICTING: sources disagree (not produced by the mock).
- NOT_VERIFIED: no claim, no certification, or unknown brand.
The EU animal-testing ban is always added as context but never raises the status.
"""

from app.common_schemas import ProductInput
from app.ethics.schemas import Certification, EthicsEvidence, EthicsResponse

CERTIFICATIONS_CHECKED = ["Leaping Bunny", "PETA Beauty Without Bunnies"]

# Open Beauty Facts labels_tags treated as brand claims (user-contributed, not verification).
CRUELTY_FREE_LABELS = {
    "en:cruelty-free",
    "en:not-tested-on-animals",
    "en:leaping-bunny",
    "en:peta-cruelty-free",
}

# Placeholder until the curated certified-brands list exists.
MOCK_CERTIFIED_BRANDS = {"mock certified brand": "Leaping Bunny"}

EU_BAN_EVIDENCE = EthicsEvidence(
    type="regulatory",
    source="Regulation (EC) No 1223/2009, Art. 18",
    detail="Animal testing of cosmetics and their ingredients is banned for products marketed in the EU.",
    source_id="eu_1223_2009_art18",
)


def build_mock_response(payload: ProductInput) -> EthicsResponse:
    brand = payload.product.brand.strip()
    common = dict(
        prompt_version="mock",
        brand=brand,
        certifications_checked=CERTIFICATIONS_CHECKED,
        warnings=payload.warnings,
    )

    if not brand:
        return EthicsResponse(
            **common,
            status="NOT_VERIFIED",
            status_reason="Brand unknown, so no claim or certification could be checked.",
            evidence=[EU_BAN_EVIDENCE],
            missing_information=["brand"],
            evidence_confidence="low",
        )

    certification = MOCK_CERTIFIED_BRANDS.get(brand.lower())
    if certification:
        return EthicsResponse(
            **common,
            status="VERIFIED",
            status_reason=f"Brand found in the {certification} certified-brands list.",
            evidence=[
                EthicsEvidence(
                    type="certification",
                    source=certification,
                    detail=f"{brand} listed as certified.",
                    source_id="mock_certified_brands",
                ),
                EU_BAN_EVIDENCE,
            ],
            certifications_found=[Certification(name=certification, source_id="mock_certified_brands")],
            evidence_confidence="high",
        )

    claim_labels = sorted(CRUELTY_FREE_LABELS.intersection(payload.product.labels))
    if claim_labels:
        return EthicsResponse(
            **common,
            status="CLAIMED",
            status_reason=(
                "Product carries a cruelty-free label on Open Beauty Facts, but the brand "
                "was not found in any certification list checked."
            ),
            evidence=[
                EthicsEvidence(
                    type="brand_claim",
                    source="Open Beauty Facts labels",
                    detail=", ".join(claim_labels),
                    source_id="obf_labels",
                ),
                EU_BAN_EVIDENCE,
            ],
            missing_information=["independent certification"],
            evidence_confidence="medium",
        )

    return EthicsResponse(
        **common,
        status="NOT_VERIFIED",
        status_reason="No cruelty-free claim or certification found for this brand.",
        evidence=[EU_BAN_EVIDENCE],
        missing_information=["brand claim", "independent certification"],
        evidence_confidence="medium",
    )
