"""Write deploy/n8n/workflows/AI-Cosmetic-Scanner.json: the scan workflow that n8n runs.

The workflow only orchestrates: every step is an HTTP call to our API (all logic and AI calls
live there). Settings come from n8n's environment: SCANNER_API_URL, SCANNER_API_KEY (n8n -> API)
and EXPO_PUBLIC_WEBHOOK_KEY (app -> n8n).

Usage: python -m scripts.build_n8n_workflow
You can also edit the workflow in the n8n editor and export it (scripts/export_workflow.sh);
then this script is no longer needed for that change.
"""

import json
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "deploy" / "n8n" / "workflows" / "AI-Cosmetic-Scanner.json"
WORKFLOW_ID = "CosmeticScan0001"  # fixed, so every deploy updates the same workflow
WEBHOOK_PATH = "cosmetic-scanner-live"

nodes: list[dict] = []
connections: dict[str, dict] = {}


def _id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cosmetic-scanner/{name}"))  # stable ids: clean diffs


def node(name, type_, version, x, y, params, **extra):
    nodes.append({"parameters": params, "id": _id(name), "name": name, "type": type_, "typeVersion": version,
                  "position": [x, y], **extra})


def link(src, dst, output=0):
    outs = connections.setdefault(src, {"main": []})["main"]
    while len(outs) <= output:
        outs.append([])
    outs[output].append({"node": dst, "type": "main", "index": 0})


def code(name, x, y, js, notes=""):
    node(name, "n8n-nodes-base.code", 2, x, y, {"jsCode": js.strip() + "\n"}, notes=notes, notesInFlow=bool(notes))


def api_call(name, x, y, path, body_expression, notes):
    """POST to our API. Second output = error (connected to 'Service failed')."""
    node(name, "n8n-nodes-base.httpRequest", 4.2, x, y, {
        "method": "POST",
        "url": f"={{{{ $env.SCANNER_API_URL + '{path}' }}}}",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-API-Key", "value": "={{ $env.SCANNER_API_KEY }}"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": body_expression,
        # The free API sleeps after 15 minutes idle and needs about a minute to wake up.
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueErrorOutput", notes=notes, notesInFlow=True)
    link(name, "Service failed", output=1)


def if_node(name, x, y, expression):
    node(name, "n8n-nodes-base.if", 2.2, x, y, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{"id": _id(name + "/cond"), "leftValue": expression, "rightValue": "",
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and",
        },
        "options": {},
    })


# ---- nodes ---------------------------------------------------------------------------

node("Scan request", "n8n-nodes-base.webhook", 2, 0, 300, {
    "httpMethod": "POST", "path": WEBHOOK_PATH, "authentication": "none", "responseMode": "responseNode",
    "options": {"allowedOrigins": "*"},  # the web app calls this from the browser (CORS)
}, webhookId=_id("webhook"), notes="Called by the app. Body: {barcode, image_ref} (or barcode_image_ref / label_image_ref for two photos).", notesInFlow=True)

code("Check request", 220, 300, r"""
// Checks the app's key and the request. Images are data URIs (data:image/...;base64,...) or https links.
const req = $input.first().json;
const body = req.body && typeof req.body === 'object' ? req.body : {};
const headers = req.headers || {};
const expected = $env.EXPO_PUBLIC_WEBHOOK_KEY || '';
const request_id = 'scan-' + $execution.id;
let error = null;
if (expected && headers['x-api-key'] !== expected) {
  error = { code: 'UNAUTHORIZED', message: 'Missing or wrong X-API-Key header.' };
}
const barcode = body.barcode == null || body.barcode === '' ? null : String(body.barcode).replace(/\s/g, '');
if (!error && barcode && !/^\d{8,14}$/.test(barcode)) {
  error = { code: 'GTIN_FORMAT', message: 'A barcode number has 8 to 14 digits.' };
}
const isRef = (r) => typeof r === 'string' && (r.startsWith('data:image/') || r.startsWith('https://'));
// image_ref: one photo that may show the barcode or the ingredient list (what the app sends, once).
const image_ref = isRef(body.image_ref) ? body.image_ref : null;
const barcode_image_ref = isRef(body.barcode_image_ref) ? body.barcode_image_ref : null;
const label_image_ref = isRef(body.label_image_ref) ? body.label_image_ref : null;
if (!error && !barcode && !image_ref && !barcode_image_ref && !label_image_ref) {
  error = { code: 'NO_INPUT', message: 'Send a barcode, a barcode photo or a photo of the ingredient list.' };
}
return [{ json: { ok: !error, request_id, error, request: { barcode, image_ref, barcode_image_ref, label_image_ref } } }];
""")

if_node("Request OK?", 440, 300, "={{ $json.ok }}")

code("Reject request", 660, 520, r"""
const c = $input.first().json;
return [{ json: { schema_version: '1.0', request_id: c.request_id,
  status: c.error.code === 'UNAUTHORIZED' ? 'unauthorized' : 'invalid_input',
  report: null, next_action: null, error: c.error } }];
""")

api_call("Read product", 660, 300, "/ingestion/scan", "={{ $json.request }}",
         "Barcode -> Open Beauty Facts; no ingredient list -> label photo OCR; names -> INCI.")

if_node("Ingredients found?", 880, 300, "={{ ($json.ingredients || []).length > 0 }}")

code("Ask for label photo", 1100, 520, r"""
const p = $input.first().json;
const c = $('Check request').first().json;
const r = c.request;
const code = (p.product && p.product.barcode) || '';
// The app sends one photo (image_ref): it may show the barcode or the ingredient list.
const onePhoto = !!r.image_ref || (!!r.label_image_ref && r.label_image_ref === r.barcode_image_ref);
const labelOnly = !!r.label_image_ref && !onePhoto;
let message;
if ((p.warnings || []).includes('product database unavailable')) {
  message = 'The product database (Open Beauty Facts) did not answer. Try again in a minute, '
    + 'or take a photo of the ingredient list on the back of the product.';
} else if (code) {
  message = 'We read the barcode ' + code + ', but Open Beauty Facts has no ingredient list for this product. '
    + 'Take a photo of the ingredient list on the back of the product.';
} else if (onePhoto) {
  message = 'We could not find a barcode or a readable ingredient list in this photo. '
    + 'Take a sharper photo of the barcode or of the ingredient list, flat and well lit, or type the barcode number.';
} else if (labelOnly) {
  message = 'The ingredient list on the photo could not be read. Take a sharper photo of the ingredient list, flat and well lit.';
} else {
  message = 'This product has no ingredient list in the product database. Take a photo of the ingredient list on the back of the product.';
}
return [{ json: { schema_version: '1.0', request_id: c.request_id, status: 'needs_input', report: null,
  product: p.product, warnings: p.warnings || [],
  next_action: { type: 'label_photo', message, barcode: code || null },
  error: null } }];
""")

api_call("Regulatory agent", 1100, 300, "/regulatory/analyze", "={{ $('Read product').first().json }}",
         "EU annexes II-VI found through the RAG index + Qwen.")
api_call("Toxicology agent", 1320, 300, "/toxicology/analyze", "={{ $('Read product').first().json }}",
         "Hazard classifications (CLP, SCCS).")
api_call("Ethics agent", 1540, 300, "/ethics/analyze", "={{ $('Read product').first().json }}",
         "Cruelty-free claims and certifications.")
api_call("Build report", 1760, 300, "/report/build",
         "={{ JSON.stringify({ product_input: $('Read product').first().json, regulatory: $('Regulatory agent').first().json, "
         "toxicology: $('Toxicology agent').first().json, ethics: $('Ethics agent').first().json }) }}",
         "Merges the three agents, attaches the source text of every claim, runs the rule checks.")
api_call("Validator agent", 1980, 300, "/report/validate", "={{ JSON.stringify({ report: $json }) }}",
         "Re-checks each claim against its source text (advisory).")

code("Public result", 2200, 300, r"""
const v = $input.first().json;
const c = $('Check request').first().json;
return [{ json: { schema_version: '1.0', request_id: c.request_id, status: v.status,
  report: v.report, validation: v.report.validation,
  validator: v.validator ? { prompt_version: v.validator.prompt_version, model: v.validator.model } : null,
  next_action: null, error: null } }];
""")

code("Service failed", 2200, 620, r"""
const e = $input.first().json;
const c = $('Check request').first().json;
const detail = (e.error && (e.error.message || e.error.description)) || e.message || 'no details';
return [{ json: { schema_version: '1.0', request_id: c.request_id, status: 'unavailable', report: null,
  next_action: null, error: { code: 'SERVICE_FAILED', message: 'A scanner service did not answer: ' + detail } } }];
""")

node("Reply", "n8n-nodes-base.respondToWebhook", 1.4, 2440, 300, {
    "respondWith": "json", "responseBody": "={{ $json }}", "options": {"responseCode": 200},
})

# ---- wiring ----------------------------------------------------------------------------

link("Scan request", "Check request")
link("Check request", "Request OK?")
link("Request OK?", "Read product", 0)
link("Request OK?", "Reject request", 1)
link("Reject request", "Reply")
link("Read product", "Ingredients found?", 0)
link("Ingredients found?", "Regulatory agent", 0)
link("Ingredients found?", "Ask for label photo", 1)
link("Ask for label photo", "Reply")
link("Regulatory agent", "Toxicology agent", 0)
link("Toxicology agent", "Ethics agent", 0)
link("Ethics agent", "Build report", 0)
link("Build report", "Validator agent", 0)
link("Validator agent", "Public result", 0)
link("Public result", "Reply")
link("Service failed", "Reply")

workflow = {
    "name": "AI Cosmetic Scanner",
    "nodes": nodes,
    "pinData": {},
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    # A new id for every content change: n8n publishes the version with this id, so a fixed id would
    # keep the old stored version live after an import.
    "versionId": _id("version/" + json.dumps([nodes, connections], sort_keys=True)),
    "meta": {"instanceId": "cosmetic-scanner"},
    "id": WORKFLOW_ID,
    "tags": [],
}

if __name__ == "__main__":
    OUT.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(OUT.parents[3])}: {len(nodes)} nodes")
