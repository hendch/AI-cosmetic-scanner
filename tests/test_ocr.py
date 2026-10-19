"""Label OCR with a fake vision model (no network, no credits)."""

import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.common import llm
from app.ingestion import extract as ex
from app.ingestion import ocr
from app.main import app

client = TestClient(app)


def photo(w=3000, h=2000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 235, 225)).save(buf, "JPEG")
    return buf.getvalue()


def data_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


@pytest.fixture
def vision(monkeypatch):
    """Fake vision model: answers from a queue, records model name and messages."""
    answers, calls = [], []

    def chat(messages, temperature=0.0, max_tokens=None, timeout=None, model=None):
        calls.append({"model": model, "messages": messages})
        return answers.pop(0)

    monkeypatch.setattr(ocr.llm, "chat", chat)
    monkeypatch.setattr(ex, "lookup_barcode", lambda code: None)  # never the network
    return answers, calls


def answer(**kw) -> str:
    base = {"readable": True, "ingredients": ["AQUA/WATER", "GLYCERIN", "PHENOXYETHAN0L"], "uncertain": [],
            "brand": "Balea", "product_name": "Body Lotion", "product_type": "body lotion"}
    return "```json\n" + json.dumps({**base, **kw}) + "\n```"


def test_image_is_shrunk_and_sent_to_the_vision_model(vision):
    answers, calls = vision
    answers.append(answer())
    body = client.post("/ingestion/scan", json={"label_image_ref": data_uri(photo())}).json()
    sent = calls[0]
    assert sent["model"] == ocr.ocr_model() == "Qwen/Qwen3-VL-30B-A3B-Instruct"
    img_part = sent["messages"][1]["content"][1]["image_url"]["url"]
    img = Image.open(io.BytesIO(base64.b64decode(img_part.split(",", 1)[1])))
    assert max(img.size) <= ocr.MAX_SIDE
    assert body["source"] == "ocr"
    assert [i["normalized"] for i in body["ingredients"]] == ["aqua", "glycerin", "phenoxyethanol"]
    assert body["product"]["brand"] == "Balea" and body["product"]["exposure_type"] == "leave_on"


def test_uncertain_names_get_low_confidence_and_review(vision):
    answers, _ = vision
    answers.append(answer(uncertain=["GLYCERIN"]))
    body = client.post("/ingestion/scan", json={"label_image_ref": data_uri(photo(400, 300))}).json()
    glycerin = next(i for i in body["ingredients"] if i["normalized"] == "glycerin")
    assert glycerin["confidence"] == ex.OCR_UNSURE_CONFIDENCE and body["needs_review"]
    assert any("hard to read" in w for w in body["warnings"])


def test_bad_json_is_retried_once(vision):
    answers, calls = vision
    answers += ["I see a label.", answer()]
    body = client.post("/ingestion/scan", json={"label_image_ref": data_uri(photo(400, 300))}).json()
    assert len(calls) == 2 and body["source"] == "ocr"


def test_unreadable_label_is_reported(vision):
    answers, _ = vision
    answers.append(answer(readable=False, ingredients=[]))
    body = client.post("/ingestion/scan", json={"label_image_ref": data_uri(photo(400, 300))}).json()
    assert body["ingredients"] == [] and body["needs_review"]
    assert "no readable ingredient list on the label photo" in body["warnings"]


def test_model_outage_is_a_warning_not_a_crash(monkeypatch):
    def down(*a, **k):
        raise llm.LLMError("Model endpoint answered HTTP 503")

    monkeypatch.setattr(ocr.llm, "chat", down)
    body = client.post("/ingestion/scan", json={"label_image_ref": data_uri(photo(400, 300))}).json()
    assert any("could not be read" in w and "503" in w for w in body["warnings"])


def test_barcode_ingredients_win_over_the_photo(vision, monkeypatch):
    _, calls = vision
    monkeypatch.setattr(ex, "lookup_barcode", lambda code: {"product_name": "X", "brands": "Y",
                                                            "ingredients_text": "Aqua, Glycerin", "categories_tags": []})
    body = client.post("/ingestion/scan", json={"barcode": "4066447870213", "label_image_ref": data_uri(photo(400, 300))}).json()
    assert body["source"] == "barcode" and not calls  # no OCR call when the database has the list


def test_one_photo_is_used_for_barcode_and_label(vision, monkeypatch):
    answers, calls = vision
    answers.append(answer())
    scanned = []
    monkeypatch.setattr("app.ingestion.router.scan_barcode", lambda data: scanned.append(data) or None)
    body = client.post("/ingestion/scan", json={"image_ref": data_uri(photo(400, 300))}).json()
    assert len(scanned) == 1  # no barcode found in the photo ...
    assert body["source"] == "ocr" and len(calls) == 1  # ... so the same photo is read as a label


def test_bad_refs_are_rejected():
    assert client.post("/ingestion/scan", json={"label_image_ref": "file:///etc/passwd"}).status_code == 422
    big = "data:image/jpeg;base64," + base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    assert client.post("/ingestion/scan", json={"label_image_ref": big}).status_code == 413


def test_non_image_is_an_ocr_error():
    with pytest.raises(ocr.OcrError):
        ocr.prepare_image(b"not an image")
