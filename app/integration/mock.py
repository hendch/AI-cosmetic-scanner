"""Mock services for the n8n scan path (replaced step by step by the real modules).

n8n REPLACES its state with each service response, so every handler must echo the
full request body and then add its own fields.
"""


def envelope(body: dict, **extra) -> dict:
    return {
        **body,
        **extra,
        "schema_version": "0.1",
        "request_id": body.get("request_id"),
        "status": "running",
    }


def product_resolve(body: dict) -> dict:
    return envelope(
        body,
        product={"category": "cosmetic", "name": "Mock Moisturizer", "brand": "MockBrand"},
        ingredients_raw="Aqua, Glycerin, Parfum, Limonene",
    )


def label_extract(body: dict) -> dict:
    return envelope(
        body,
        ingredients_raw="Aqua, Glycerin, Parfum, Limonene",
        ocr={"needs_confirmation": False},
    )


def ingredients_normalize(body: dict) -> dict:
    return envelope(body, ingredients=[
        {"ingredient_id": "aqua", "name": "Aqua", "concentration_percent": None},
        {"ingredient_id": "glycerin", "name": "Glycerin", "concentration_percent": None},
        {"ingredient_id": "parfum", "name": "Parfum", "concentration_percent": None},
        {"ingredient_id": "limonene", "name": "Limonene", "concentration_percent": None},
    ])


def evidence_retrieve(body: dict) -> dict:
    assessment_date = (body.get("input") or {}).get("assessment_date", "2026-10-15")
    corpus_version = (body.get("config") or {}).get("corpus_version", "v0-test")
    return envelope(body, evidence_pack={
        "corpus_version": corpus_version,
        "as_of": assessment_date,
        "is_synthetic": False,
        "sources": [
            {"evidence_id": "ev-aqua-1", "kind": "regulation", "ingredient_ids": ["aqua"],
             "source_url": "https://example.org/eu-reg/aqua", "source_version": "2024",
             "excerpt": "Aqua is permitted in cosmetic products without restriction.",
             "retrieved_at": "2026-10-15", "applicability_verified": True, "is_synthetic": False},
            {"evidence_id": "ev-limonene-tox-1", "kind": "toxicology", "ingredient_ids": ["limonene"],
             "source_url": "https://example.org/sccs/limonene", "source_version": "2023",
             "excerpt": "Limonene is a known skin sensitizer at higher concentrations.",
             "retrieved_at": "2026-10-15", "applicability_verified": True, "is_synthetic": False},
        ],
        "rules": [
            {"ingredient_id": "limonene", "rule_state": "conditional",
             "concentration_required": True, "condition_result": "unknown",
             "evidence_ids": ["ev-limonene-tox-1"]},
        ],
        "lookup_log": [
            {"ingredient_id": i, "exact_lookup_complete": True}
            for i in ("aqua", "glycerin", "parfum", "limonene")
        ],
    })
