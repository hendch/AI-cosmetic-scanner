# n8n ⇄ FastAPI contract  (schema_version `0.1`)

Source of truth in code: `app/integration/schemas.py` (Pydantic v2). Check with `pytest tests/test_integration.py`.

## Golden rules
1. n8n POSTs the **whole envelope** as JSON to each endpoint.
2. n8n **replaces its state with your response**. Echo the full request body, then add your fields.
   (If you return only your new fields, earlier data such as `product` / `ingredients` is lost.)
3. Always return `schema_version: "0.1"`, the same `request_id`, and `status: "running"`.
4. Never return an `error` key on success. An error key, wrong `request_id` or missing `status` makes n8n return `unavailable`.
5. n8n overwrites `config`, `origin`, `mode`, `input` after each call. Services cannot change them.

## Envelope (request body)
`schema_version, request_id, status, action, mode, origin, config{live_integrations_ready, service_base_url, corpus_version, prompt_version, embedding_revision}, input{barcode, barcode_image_ref, label_image_ref, market:"EU", assessment_date}, trace`

## Endpoints (scan path)
| Endpoint | Called when | Add to response | Rejected if |
|---|---|---|---|
| `POST /v1/product/resolve` | always, first | `product{category:"cosmetic",name,brand}`, `ingredients_raw` (nullable) | `product.category != cosmetic` → `PRODUCT_CONTRACT` |
| `POST /v1/label/extract` | no `ingredients_raw` and `label_image_ref` set | `ingredients_raw`, `ocr{needs_confirmation:false}` | missing `ingredients_raw` or `needs_confirmation != false` → `OCR_CONTRACT` |
| `POST /v1/ingredients/normalize` | always | `ingredients[]{ingredient_id,name,concentration_percent}` (1–50, unique ids) | empty / >50 → `NORMALIZATION_CONTRACT` |
| `POST /v1/evidence/retrieve` | always | `evidence_pack{corpus_version,as_of,is_synthetic:false,sources[],rules[],lookup_log[]}` | missing parts → `EVIDENCE_CONTRACT`; provenance problems → `EVIDENCE_PROVENANCE` |
| `GET /health` | never (healthcheck only) | `{ok:true}` | – |

### Evidence provenance rules
- `evidence_pack.corpus_version == config.corpus_version` and `evidence_pack.as_of == input.assessment_date`
- every source: unique `evidence_id`, `is_synthetic:false`, `https://` `source_url`, `source_version`, `excerpt`, `retrieved_at`, `ingredient_ids[]`, `applicability_verified:true`
- every `source.ingredient_ids` entry exists in `ingredients[]`
- `rules[]`: `{ingredient_id, rule_state, concentration_required, condition_result(unknown|satisfied|not_satisfied|not_assessed), evidence_ids[]}`
- `lookup_log[]`: `{ingredient_id, exact_lookup_complete}` (a "no rule found" claim needs `exact_lookup_complete:true`)

## Endpoints (ingest path, `action:"ingest"`, manual only)
`POST /v1/corpus/parse` → `/chunk` → `/stage` → `/activate`. Final response needs `status:"completed"` and `corpus.activated_version`, `corpus.counts`, checks. Otherwise `CORPUS_NOT_ACTIVATED`.
`evaluate` has no endpoint (computed in an n8n Code node from `evaluation_input`).

## Public webhook
`POST /webhook/cosmetic-scanner-live` with header `X-API-Key: <secret>`, body `{barcode, barcode_image_ref, label_image_ref, market:"EU", assessment_date}`.
Response: `{schema_version, request_id, action, mode, origin, status, report, result, next_action, error{code,message}, validation}`.
`report` is non-null only when `status == "completed"`.

## Status values
`completed` · `needs_input` (e.g. upload a label) · `invalid_input` · `setup_required` · `needs_review` (evidence/agent output failed a gate) · `unavailable` (a service failed)

## error.code values
`RUN_SETTINGS, SCHEMA, SCOPE, GTIN_FORMAT, GTIN_CHECKSUM, NO_INPUT, PRODUCT_FAILED, PRODUCT_CONTRACT, OCR_FAILED, OCR_CONTRACT, NORMALIZATION_FAILED, NORMALIZATION_CONTRACT, EVIDENCE_FAILED, EVIDENCE_CONTRACT, EVIDENCE_PROVENANCE, AGENT_JSON, AGENT_COVERAGE, AGENT_SCHEMA, CORPUS_NOT_ACTIVATED` (plus codes raised by the validator/final gates).
