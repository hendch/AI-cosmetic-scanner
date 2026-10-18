from fastapi.testclient import TestClient

from app.common_schemas import ProductInput
from app.main import app
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
    assert [i.normalized for i in body.ingredients] == ["aqua", "phenoxyethanol", "retinol", "parfum"]
    assert all(i.matched and i.confidence == 1.0 for i in body.ingredients)
    assert body.needs_review is False         # every name recognised exactly


def test_nothing_found():
    r = client.post("/ingestion/extract")
    body = ProductInput.model_validate(r.json())
    assert body.source is None
    assert body.needs_review is True
    assert "no barcode detected" in body.warnings


def test_barcode_must_be_digits(monkeypatch):
    called = []
    monkeypatch.setattr(ex.requests, "get", lambda *a, **k: called.append(a))
    assert ex.lookup_barcode("../../../samples/input/barcode_found") is None
    assert not called  # never reaches the cache file name or the network


def test_network_failure_is_reported_not_crashed(monkeypatch):
    def down(*a, **k):
        raise ex.requests.ConnectionError("offline")

    monkeypatch.setattr(ex.requests, "get", down)
    body = client.post("/ingestion/extract", data={"barcode": "99999999"}).json()
    assert "barcode not found or no ingredients" in body["warnings"]


def test_product_name_is_the_fallback_category(monkeypatch):
    product = {**FAKE_PRODUCT, "product_name": "Bodylotion Creme-Öl", "categories_tags": []}
    monkeypatch.setattr(ex, "lookup_barcode", lambda code: product)
    body = client.post("/ingestion/extract", data={"barcode": "123"}).json()
    assert body["product"]["category"] == "bodylotion creme-öl"
    assert body["product"]["exposure_type"] == "leave_on"
