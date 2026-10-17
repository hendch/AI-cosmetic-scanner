"""Calls the mock the way n8n does and validates every response against the contract."""
import pytest
from fastapi.testclient import TestClient

from app.integration.schemas import (EvidenceResponse, LabelExtractResponse,
                                     NormalizeResponse, ProductResolveResponse)
from app.main import app

client = TestClient(app)

STATE = {
    "schema_version": "0.1", "request_id": "cosmetic-1", "status": "running",
    "action": "scan", "mode": "live", "origin": "manual",
    "config": {"live_integrations_ready": True, "service_base_url": "http://scanner-api:8000",
               "corpus_version": "v0-test", "prompt_version": "v2", "embedding_revision": "bge-m3-test"},
    "input": {"barcode": "4006381333931", "barcode_image_ref": None, "label_image_ref": "img1",
              "market": "EU", "assessment_date": "2026-10-16"},
    "trace": [],
}


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_scan_path_holds_the_contract():
    state = STATE
    for path, model in [("/v1/product/resolve", ProductResolveResponse),
                        ("/v1/label/extract", LabelExtractResponse),
                        ("/v1/ingredients/normalize", NormalizeResponse),
                        ("/v1/evidence/retrieve", EvidenceResponse)]:
        response = client.post(path, json=state).json()
        model.model_validate(response)
        # what n8n's envelope nodes do between calls
        state = {**response, "config": STATE["config"], "input": STATE["input"]}
    assert [i["ingredient_id"] for i in state["ingredients"]] == ["aqua", "glycerin", "parfum", "limonene"]
