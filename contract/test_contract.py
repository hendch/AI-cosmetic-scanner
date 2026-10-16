"""Run:  pip install fastapi httpx pydantic && python contract/test_contract.py
Calls the mock the way n8n does and validates every response against the contract."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "scanner_api"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "contract"))
from fastapi.testclient import TestClient
from mock_service import app
from models import (ProductResolveResponse, LabelExtractResponse,
                    NormalizeResponse, EvidenceResponse)

c = TestClient(app)
state = {
    "schema_version": "0.1", "request_id": "cosmetic-1", "status": "running",
    "action": "scan", "mode": "live", "origin": "manual",
    "config": {"live_integrations_ready": True, "service_base_url": "http://scanner-api:8000",
               "corpus_version": "v0-test", "prompt_version": "v2", "embedding_revision": "bge-m3-test"},
    "input": {"barcode": "4006381333931", "barcode_image_ref": None, "label_image_ref": "img1",
              "market": "EU", "assessment_date": "2026-10-16"},
    "trace": [],
}
for path, model in [("/v1/product/resolve", ProductResolveResponse),
                    ("/v1/label/extract", LabelExtractResponse),
                    ("/v1/ingredients/normalize", NormalizeResponse),
                    ("/v1/evidence/retrieve", EvidenceResponse)]:
    r = c.post(path, json=state).json()
    model.model_validate(r)
    state = {**r, "config": state["config"], "input": state["input"]}  # what n8n's envelope nodes do
    print("OK ", path)
print("contract holds; ingredients carried through:", [i["ingredient_id"] for i in state["ingredients"]])
