# Regulatory agent: interfaces

Owner: Kreemi. Module: `app/regulatory/`. Endpoint: `POST /regulatory/analyze`.

Every dependency on another teammate goes through one placeholder with the exact format
below. When the real part is ready, it is switched on with a setting, not a code change.

| Dependency | Placeholder today | Switch to the real thing |
|---|---|---|
| Product input (Muaadh) | `samples/input/*.json` | nothing: same `ProductInput` format |
| Retrieval (Haroun) | `RETRIEVAL_BACKEND=local` reads `corpus/regulatory/` | `RETRIEVAL_BACKEND=http`, `RETRIEVAL_URL=<his service>` |
| LLM (shared) | `REGULATORY_MODE=mock` (rules only) | `REGULATORY_MODE=live` + `.env` from `.env.example` |
| n8n (Lyna) | call the endpoint yourself on `/docs` | one HTTP node per agent |
| Report (Omar) | `samples/regulatory/*.json` | same format from the live endpoint |

## Input: from Muaadh (barcode/OCR)

`ProductInput` from `app/common_schemas.py`, unchanged. What the regulatory agent uses:

- `product.category` (text, e.g. `"face cream"`, `"shampoo"`): matched against annex product types
  such as "(b) Other products except body lotion, ...". Without it, product-type conditions are `unknown`.
- `product.exposure_type`: `"leave_on"` or `"rinse_off"`. Decides "Rinse-off products only" entries.
- `ingredients[].normalized`: lowercase INCI (e.g. `methylisothiazolinone`, `zinc pyrithione`).
  Aliases accepted by the agent are in `corpus/regulatory/regulatory_scope.csv`; please reuse them
  in the normalizer (e.g. water -> aqua, pyrithione zinc -> zinc pyrithione).
- `ingredients[].matched` and `confidence`: unmatched -> `not_assessed`; confidence < 0.8 -> low confidence.
- Optional, later: `ingredients[].concentration_percent` (number). The agent already reads it if present.

## Retrieval: from Haroun (RAG)

What I give: `corpus/regulatory/` (one CSV row per annex entry, plus Articles 15, 16, 18), registered in
`corpus/sources.csv`. One annex row = one structure-aware chunk.

What the agent calls (`app/regulatory/retrieval.py`):

```
POST {RETRIEVAL_URL}/retrieval/search
{"query": "methylisothiazolinone restrictions conditions of use leave-on",
 "filters": {"doc_type": "regulation", "ingredient": "methylisothiazolinone"},
 "top_k": 5}
```

Expected answer:

```
{"results": [
  {"chunk_id": "eu_1223_2009_annex_v#57",
   "source_id": "eu_1223_2009_annex_v",
   "text": "Regulation (EC) No 1223/2009, Annex V, entry 57 ...",
   "score": 0.83,
   "metadata": {"doc_type": "regulation",
                "ingredients": "methylisothiazolinone",
                "annex": "V", "entry": "57",
                "product_type_body_parts": "Rinse-off products",
                "max_concentration": "0,0015 %",
                "other_conditions": "", "warnings": "",
                "consolidated_version": "2026-05-18",
                "source_url": "https://eur-lex.europa.eu/..."}}]}
```

Requirements:
1. The `ingredient` filter works on normalized INCI names (`ingredients` may hold several, `;`-separated).
2. `source_id` = corpus filename without extension (team convention), so citations can be checked.
3. `annex` and `entry` are always in the metadata. The agent takes the legal status from the annex
   (II = prohibited, III-VI = restricted). Chunks without them are ignored.
4. The condition fields above are copied from the CSV columns. Without them, conditions cannot be checked.
5. Nothing found = `{"results": []}`.

For your evaluation: test questions with expected sources are in `eval/regulatory/retrieval_questions.json`.

## Output: to Omar (report) and Lyna (n8n)

`RegulatoryResponse` (`app/regulatory/schemas.py`). Examples in `samples/regulatory/`.

Per ingredient (`findings[]`):

| Field | Values |
|---|---|
| `regulatory_status` | `prohibited` (Annex II) / `restricted` (Annex III-VI) / `no_restriction_found` / `not_assessed` |
| `entries[]` | `{annex, entry, source_id}`, e.g. `V`, `57`, `eu_1223_2009_annex_v` |
| `conditions[]` | `{entry, type, requirement, result, reason}`; type: `product_type`, `max_concentration`, `usage`, `labelling`; result: `satisfied`, `not_satisfied`, `unknown`, `not_applicable` |
| `compliance_check` | `not_satisfied` if any condition fails or prohibited, else `unknown` if any is unknown, else `satisfied`; `not_applicable` when nothing to check |
| `explanation` | 1-2 sentences, never "safe/unsafe/illegal" |
| `missing_information`, `evidence_confidence`, `sources` | same names as the toxicology agent |

Response level: `warnings` (input warnings + agent warnings) and `run` (mode, model, LLM calls,
retries, fallbacks, overrides) for evaluation and debugging. Not for consumers.

Citation check: every `sources[]` and `entries[].source_id` is a `source_id` in `corpus/sources.csv`.
`regulatory_scope` is cited for `no_restriction_found`.

For n8n: one call per product, typically 1-5 s per restricted ingredient (LLM calls run in parallel);
set the HTTP timeout to 60 s. The endpoint never fails because of the LLM: if it is unreachable, the
agent returns the rule-based result with a warning.

## Hind (toxicology/ethics)

- Split: regulatory = legal status (annexes, Art. 15 CMR rule); toxicology = hazards (CLP, SCCS).
- `eu_1223_2009_art18` (animal testing) is now a real corpus file for the ethics agent to cite.
- Shared files changed: `app/dev_server.py` and `scripts/generate_samples.py` (one line each to add the
  regulatory module), and a new sample `samples/input/leave_on_restricted.json` (so the toxicology and
  ethics samples gained one file each).
- Proposal: reuse `app/regulatory/llm.py` (OpenAI-compatible client + YAML prompt loader) as a shared
  `app/llm_client.py`.

## How the agent works (summary)

1. Gate (code): unmatched or out-of-scope ingredient -> `not_assessed`.
2. Retrieve (Haroun / placeholder): annex entries for the ingredient.
3. Status (code): from the annex. Prohibited and "no restriction" need no LLM call.
4. Product type (code): the category is matched to the lettered items of the entry
   (7B models misread "Other products except ..."; see `prompts/regulatory/v3.yaml`).
5. Interpret (LLM, prompt v4): every remaining condition -> result + reason + explanation.
6. Validate (code): schema, coverage, citations, wording; safety rules override the LLM
   (unknown concentration stays unknown, label warnings are never decided without the label,
   rule-decided product types win); one retry; conservative fallback.
