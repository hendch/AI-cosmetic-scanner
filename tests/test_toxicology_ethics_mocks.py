import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ethics.schemas import EthicsResponse
from app.toxicology.schemas import ToxicologyResponse

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
INPUTS = sorted((SAMPLES / "input").glob("*.json"))

client = TestClient(app)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("input_file", INPUTS, ids=lambda p: p.stem)
def test_toxicology_endpoint_returns_valid_response(input_file):
    response = client.post("/toxicology/analyze", json=_load(input_file))
    assert response.status_code == 200
    ToxicologyResponse.model_validate(response.json())


@pytest.mark.parametrize("input_file", INPUTS, ids=lambda p: p.stem)
def test_ethics_endpoint_returns_valid_response(input_file):
    response = client.post("/ethics/analyze", json=_load(input_file))
    assert response.status_code == 200
    EthicsResponse.model_validate(response.json())


def test_unmatched_and_low_confidence_ingredients_are_flagged():
    findings = client.post("/toxicology/analyze", json=_load(SAMPLES / "input" / "ocr_unknown_brand.json")).json()["findings"]
    by_name = {f["ingredient"]: f for f in findings}
    assert by_name["xyl0-blend"]["concern_level"] == "insufficient_evidence"
    assert by_name["phenoxyethanol"]["evidence_confidence"] == "low"
    assert "ingredient name from OCR, unverified" in by_name["phenoxyethanol"]["missing_information"]


@pytest.mark.parametrize(
    "input_name, expected_status",
    [
        ("clean_product.json", "NOT_VERIFIED"),  # "Mock Certified Brand" is on no real list
        ("sensitiser_claimed.json", "CLAIMED"),
        ("ocr_unknown_brand.json", "NOT_VERIFIED"),
    ],
)
def test_ethics_status_rules(input_name, expected_status):
    body = client.post("/ethics/analyze", json=_load(SAMPLES / "input" / input_name)).json()
    assert body["status"] == expected_status
    assert any(e["type"] == "regulatory" for e in body["evidence"])
