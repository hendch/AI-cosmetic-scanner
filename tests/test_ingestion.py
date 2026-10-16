from fastapi.testclient import TestClient

from app.common_schemas import ProductInput
from app.dev_server import app
from app.ingestion import extract as ex

client = TestClient(app)

FAKE_PRODUCT = {
    "product_name": "Hydra Cream", "brands": "Acme",
    "ingredients_text": "Aqua, Phenoxyethanol, Retinol, Parfum (Fragrance)",
    "categories_tags": ["en:face-creams"], "labels_tags": ["en:vegan"],
}


def test_barcode_found(monkeypatch):
    monkeypatch.setattr(ex, "lookup_barcode", lambda code: FAKE_PRODUCT)
    r = client.post("/ingestion/extract", data={"barcode": "123"})
    assert r.status_code == 200
    body = ProductInput.model_validate(r.json())
    assert body.source == "barcode"
    assert body.product.exposure_type == "leave_on"
    assert [i.normalized for i in body.ingredients if i.matched] == ["phenoxyethanol", "retinol"]
    assert body.needs_review is True          # aqua / parfum are not in KNOWN


def test_nothing_found():
    r = client.post("/ingestion/extract")
    body = ProductInput.model_validate(r.json())
    assert body.source == "none"
    assert body.needs_review is True
    assert "no barcode detected" in body.warnings
