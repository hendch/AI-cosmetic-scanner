import csv
import os

os.environ["REGULATORY_MODE"] = "mock"  # tests never call the LLM
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.regulatory.schemas import RegulatoryResponse

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
INPUTS = sorted((SAMPLES / "input").glob("*.json"))

client = TestClient(app)


def _load(name: str) -> dict:
    return json.loads((SAMPLES / "input" / name).read_text(encoding="utf-8"))


def _findings(name: str) -> dict:
    body = client.post("/regulatory/analyze", json=_load(name)).json()
    return {f["ingredient"]: f for f in body["findings"]}


@pytest.mark.parametrize("input_file", INPUTS, ids=lambda p: p.stem)
def test_regulatory_endpoint_returns_valid_response(input_file):
    payload = json.loads(input_file.read_text(encoding="utf-8"))
    response = client.post("/regulatory/analyze", json=payload)
    assert response.status_code == 200
    body = RegulatoryResponse.model_validate(response.json())
    assert len(body.findings) == len(payload["ingredients"])


def test_every_cited_source_is_registered():
    with (ROOT / "corpus" / "sources.csv").open(encoding="utf-8") as f:
        known = {row["source_id"] for row in csv.DictReader(f)}
    for input_file in INPUTS:
        body = client.post("/regulatory/analyze", json=json.loads(input_file.read_text(encoding="utf-8"))).json()
        for finding in body["findings"]:
            assert set(finding["sources"]) <= known
            assert {e["source_id"] for e in finding["entries"]} <= known


def test_rinse_off_only_preservative_depends_on_product_type():
    shampoo = _findings("sensitiser_claimed.json")["methylisothiazolinone"]
    cream = _findings("leave_on_restricted.json")["methylisothiazolinone"]
    assert shampoo["regulatory_status"] == cream["regulatory_status"] == "restricted"
    assert shampoo["compliance_check"] == "unknown"  # rinse-off ok, concentration unknown
    assert cream["compliance_check"] == "not_satisfied"  # leave-on not allowed


def test_annex_ii_substance_is_prohibited():
    zpt = _findings("leave_on_restricted.json")["zinc pyrithione"]
    assert zpt["regulatory_status"] == "prohibited"
    assert zpt["entries"][0] == {"annex": "II", "entry": "1670", "source_id": "eu_1223_2009_annex_ii"}


def test_unknown_concentration_is_never_satisfied():
    for input_file in INPUTS:
        body = client.post("/regulatory/analyze", json=json.loads(input_file.read_text(encoding="utf-8"))).json()
        for finding in body["findings"]:
            for c in finding["conditions"]:
                if c["type"] == "max_concentration":
                    assert c["result"] == "unknown"
            if any(c["type"] == "max_concentration" for c in finding["conditions"]):
                assert "concentration" in finding["missing_information"]


def test_no_restriction_vs_not_covered():
    f = _findings("leave_on_restricted.json")
    assert f["niacinamide"]["regulatory_status"] == "no_restriction_found"
    assert f["niacinamide"]["sources"] == ["regulatory_scope"]
    # sodium benzoate: Annex V/1 (corpus extended 2026-10-18); before that it was out of scope
    assert f["sodium benzoate"]["regulatory_status"] == "restricted"
    assert f["sodium benzoate"]["entries"][0] == {"annex": "V", "entry": "1", "source_id": "eu_1223_2009_annex_v"}
    # still out of scope: a recognised ingredient the corpus does not cover
    assert _findings("barcode_found.json")["parfum"]["regulatory_status"] == "not_assessed"


def test_unmatched_and_low_confidence_ingredients():
    f = _findings("ocr_unknown_brand.json")
    assert f["xyl0-blend"]["regulatory_status"] == "not_assessed"
    assert f["phenoxyethanol"]["evidence_confidence"] == "low"
    assert "ingredient name from OCR, unverified" in f["phenoxyethanol"]["missing_information"]


@pytest.mark.parametrize(
    "requirement, category, exposure, expected",
    [
        ("(a) Rinse-off hair products (b) Other products except body lotion, eye shadow, mascara, eyeliner, lipstick, roll-on deodorant (c) Body lotion, eye shadow, mascara, eyeliner, lipstick, roll-on deodorant",
         "face cream", "leave_on", ("b", True)),
        ("(a) Rinse-off hair products (b) Other products except body lotion, eye shadow, mascara, eyeliner, lipstick, roll-on deodorant (c) Body lotion, eye shadow, mascara, eyeliner, lipstick, roll-on deodorant",
         "body lotion", "leave_on", ("c", True)),
        ("(a) Rinse-off hair products (b) Other products except body lotion", "shampoo", "rinse_off", ("a", True)),
        ("(a) Body lotion (b) other leave-on and rinse-off products", "face cream", "leave_on", ("b", True)),
        ("a) Mouthwash b) Toothpaste c) Other leave-on and rinse-off products", "toothpaste", "rinse_off", ("b", True)),
        ("Face products with the exception of propellent spray products", "body lotion", "leave_on", (None, False)),
        ("Face products with the exception of propellent spray products", "face cream", "leave_on", ("", True)),
        ("a) Face products, hand products, and lip products, excluding propellant and pump spray products b) Body products, including propellant and pump spray products c) Other products",
         "lipstick", "leave_on", ("a", True)),
        ("(a) Body lotion (b) other leave-on and rinse-off products", None, None, (None, None)),
    ],
)
def test_product_type_matching(requirement, category, exposure, expected):
    from app.common_schemas import Product
    from app.regulatory.rules import match_product_type

    assert match_product_type(requirement, Product(category=category, exposure_type=exposure)) == expected


def test_evaluation_runs_in_mock_mode():
    from scripts.eval_regulatory import evaluate

    r = evaluate("mock", None)
    assert r["status_accuracy"] == 100.0 and r["citation_validity"] == 100.0 and r["wording_violations"] == 0


def test_router_loads_dotenv_before_choosing_the_mode():
    # .env (REGULATORY_MODE, HF_TOKEN) is loaded by app.common.llm; the router must import it,
    # otherwise the API stays in mock mode even with a configured .env. Fresh interpreter, since
    # the other test modules already import llm.
    import subprocess
    import sys

    code = "import sys, app.regulatory.router; print('app.common.llm' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"


# ---- fixes on the end-to-end branch (2026-10-18) ---------------------------------------

SALICYLIC = ("(a) Rinse-off hair products (b) Other products except body lotion, eye shadow, mascara, eyeliner, "
             "lipstick, roll-on deodorant (c) Body lotion, eye shadow, mascara, eyeliner, lipstick, roll-on deodorant")
BENZOATES = "(a) Rinse-off products, except oral products (b) Oral products (c) Leave-on products"


@pytest.mark.parametrize(
    "requirement, category, exposure, expected",
    [
        # An exclusion needs ALL its words: "body lotion" does not exclude "body cream" (was a false "not allowed").
        (SALICYLIC, "body cream", "leave_on", ("b", True)),
        (SALICYLIC, "eye cream", "leave_on", ("b", True)),
        (SALICYLIC, "body lotion", "leave_on", ("c", True)),
        # No body area in the category: cannot tell face from body (was a false "not allowed").
        ("Face products with the exception of propellent spray products", "sunscreens", "leave_on", (None, None)),
        ("Face products with the exception of propellent spray products", "body sunscreen spray", "leave_on", (None, False)),
        (BENZOATES, "toothpaste", "rinse_off", ("b", True)),
        (BENZOATES, "shower gel", "rinse_off", ("a", True)),
        (BENZOATES, "body lotion", "leave_on", ("c", True)),
    ],
)
def test_product_type_matching_fixes(requirement, category, exposure, expected):
    from app.common_schemas import Product
    from app.regulatory.rules import match_product_type

    assert match_product_type(requirement, Product(category=category, exposure_type=exposure)) == expected


def test_concentration_reaches_the_agent_and_is_compared():
    payload = json.loads((SAMPLES / "input" / "clean_product.json").read_text(encoding="utf-8"))
    for ing in payload["ingredients"]:
        if ing["normalized"] == "phenoxyethanol":
            ing["concentration_percent"] = 0.8
    phenoxy = {f["ingredient"]: f for f in client.post("/regulatory/analyze", json=payload).json()["findings"]}["phenoxyethanol"]
    conc = next(c for c in phenoxy["conditions"] if c["type"] == "max_concentration")
    assert conc["result"] == "satisfied" and "1 %" in conc["reason"]  # V/29: 1,0 %
    assert "concentration" not in phenoxy["missing_information"]


def test_multi_value_limits_are_not_compared_by_rule():
    from app.regulatory.rules import single_limit

    assert single_limit("1,0 %") == 1.0 and single_limit("0,6 % (acid)") == 0.6
    assert single_limit("(a) 2,5 % (acid) (b) 1,7 % (acid) (c) 0,5 % (acid)") is None
    assert single_limit("0,4 % (as acid) for single ester 0,8 % (as acid) for mixtures of esters") is None


def test_new_annex_entries():
    f = _findings("leave_on_restricted.json")
    assert [e["entry"] for e in f["sodium benzoate"]["entries"]] == ["1"]
    from app.regulatory.kb import load_kb

    kb = load_kb()
    assert {r.ref for r in kb.entries_for("isopropylparaben")} == {"II/1374"}
    assert {r.ref for r in kb.entries_for("benzyl alcohol")} == {"III/45", "V/34"}
    assert kb.canonical("potassium sorbate") == "potassium sorbate"
