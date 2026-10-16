from fastapi import FastAPI, Request

app = FastAPI(title="Cosmetic Scanner Mock")


def envelope(body, **extra):
    """n8n REPLACES its state with each service response, so every service must
    echo the full request body and then add its own fields."""
    return {
        **body,
        **extra,
        "schema_version": "0.1",
        "request_id": body.get("request_id"),
        "status": "running",
    }


@app.post("/v1/product/resolve")
async def product_resolve(req: Request):
    body = await req.json()
    return envelope(body,
        product={"category": "cosmetic", "name": "Mock Moisturizer", "brand": "MockBrand"},
        ingredients_raw="Aqua, Glycerin, Parfum, Limonene",
    )


@app.post("/v1/label/extract")
async def label_extract(req: Request):
    body = await req.json()
    return envelope(body,
        ingredients_raw="Aqua, Glycerin, Parfum, Limonene",
        ocr={"needs_confirmation": False},
    )


@app.post("/v1/ingredients/normalize")
async def ingredients_normalize(req: Request):
    body = await req.json()
    return envelope(body, ingredients=[
        {"ingredient_id": "aqua",     "name": "Aqua",     "concentration_percent": None},
        {"ingredient_id": "glycerin", "name": "Glycerin", "concentration_percent": None},
        {"ingredient_id": "parfum",   "name": "Parfum",   "concentration_percent": None},
        {"ingredient_id": "limonene", "name": "Limonene", "concentration_percent": None},
    ])


@app.post("/v1/evidence/retrieve")
async def evidence_retrieve(req: Request):
    body = await req.json()
    ad = (body.get("input") or {}).get("assessment_date", "2026-10-15")
    cv = (body.get("config") or {}).get("corpus_version", "v0-test")
    return envelope(body, evidence_pack={
        "corpus_version": cv,
        "as_of": ad,
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
            {"ingredient_id": "aqua",     "exact_lookup_complete": True},
            {"ingredient_id": "glycerin", "exact_lookup_complete": True},
            {"ingredient_id": "parfum",   "exact_lookup_complete": True},
            {"ingredient_id": "limonene", "exact_lookup_complete": True},
        ],
    })


@app.get("/health")
async def health():
    return {"ok": True}
