# n8n: the scan workflow

n8n runs one workflow, **AI Cosmetic Scanner** (`deploy/n8n/workflows/AI-Cosmetic-Scanner.json`).
It only orchestrates: every step is an HTTP call to our API, where all the logic and AI calls live.

```
Scan request (webhook, POST /webhook/cosmetic-scanner-live)
 → Check request          app key, barcode format (8-14 digits), photo format
 → Read product           POST /ingestion/scan       barcode → Open Beauty Facts; no list → label photo (OCR)
 → Ingredients found?     no → answer needs_input: "take a photo of the ingredient list"
 → Regulatory agent       POST /regulatory/analyze
 → Toxicology agent       POST /toxicology/analyze
 → Ethics agent           POST /ethics/analyze
 → Build report           POST /report/build         merge + source text + rule checks
 → Validator agent        POST /report/validate      AI re-check of each claim (advisory)
 → Public result → Reply
Any API call that fails → Service failed → Reply (status unavailable)
```

## Running it

- **Locally:** `docker compose up -d --build` (fill `.env` from `.env.example` first). n8n: http://localhost:5678.
- **On Render:** see `docs/DEPLOY.md`.

At every start, n8n imports the workflow file from git and publishes it (`deploy/n8n/start.sh`), so nothing has to
be imported or activated by hand. No n8n credentials are needed: the keys come from environment variables.

| Variable (n8n) | What |
|---|---|
| `SCANNER_API_URL` | Address of our API (`http://scanner-api:8000` in docker compose, the Render URL online) |
| `SCANNER_API_KEY` | Sent as `X-API-Key` on every API call |
| `EXPO_PUBLIC_WEBHOOK_KEY` | The key the app must send; if empty, the webhook accepts any request |

## Changing the workflow

Either edit `scripts/build_n8n_workflow.py` and run `python -m scripts.build_n8n_workflow`, or edit it in the n8n
editor and export it with `scripts/export_workflow.sh`. Commit the JSON file; the next deploy uses it.

## What the app sends and receives

**Request:** `POST /webhook/cosmetic-scanner-live`, headers `Content-Type: application/json` and
`X-API-Key: <EXPO_PUBLIC_WEBHOOK_KEY>`.

```json
{"barcode": "4066447870213", "barcode_image_ref": null, "label_image_ref": null}
```

Send at least one. Photos are `data:image/jpeg;base64,...` (or an `https://` link), at most 10 MB.

**Answer (always HTTP 200; read `status`):**

```json
{"schema_version": "1.0", "request_id": "scan-123", "status": "completed",
 "report": { ... see app/report/schemas.py: Report ... },
 "validation": { "passed": true, "checks": [ ... ] },
 "validator": {"prompt_version": "v5", "model": "Qwen/Qwen2.5-7B-Instruct:featherless-ai"},
 "next_action": null, "error": null}
```

| `status` | Meaning | What the app does |
|---|---|---|
| `completed` | Report built, all rule checks passed | Show the report |
| `needs_review` | Report built, but an error-level rule check failed | Show the report with the failed checks |
| `needs_input` | No ingredient list (barcode unknown, or photo unreadable) | Show `next_action.message`, ask for a label photo |
| `invalid_input` | Bad barcode or no input | Show `error.message` |
| `unauthorized` | Wrong or missing app key | Configuration problem |
| `unavailable` | An API call failed | Show `error.message`, offer to retry |

## Tested (local docker compose, 2026-10-18)

| Request | Answer |
|---|---|
| No key | `unauthorized` |
| Barcode `12ab` | `invalid_input` (GTIN_FORMAT) |
| Barcode not in Open Beauty Facts | `needs_input` with the label-photo message |
| Balea barcode 4066447870213 | `completed`: 15 ingredients, 3 restricted (6.5 s, rules-only regulatory) |
| CeraVe label photo only | `completed` via OCR: 25 ingredients, 2 restricted (21 s) |
| Browser CORS pre-check | 204 with `Access-Control-Allow-Origin` for the app's origin |
| API stopped | `unavailable` with the reason |
