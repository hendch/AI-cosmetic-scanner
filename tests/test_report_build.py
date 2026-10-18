"""/report/build and /report/validate on the real agents' outputs (fake model: no credits).

Each sample in samples/input goes through /regulatory (rules only), /toxicology and /ethics,
then into the report, exactly as n8n chains them.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.common import llm
from app.main import app
from app.report import agent
from app.report.schemas import Report

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "input"
client = TestClient(app)


@pytest.fixture(autouse=True)
def rules_only(monkeypatch):
    monkeypatch.setenv("REGULATORY_MODE", "mock")


def chain(name: str) -> dict:
    product = json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    req = {"product_input": product}
    for agent_name in ("regulatory", "toxicology", "ethics"):
        r = client.post(f"/{agent_name}/analyze", json=product)
        assert r.status_code == 200, r.text
        req[agent_name] = r.json()
    return req


def build(name: str) -> dict:
    r = client.post("/report/build", json=chain(name))
    assert r.status_code == 200, r.text
    Report.model_validate(r.json())
    return r.json()


def check(report: dict, name: str) -> dict:
    return next(c for c in report["validation"]["checks"] if c["name"] == name)


@pytest.mark.parametrize("name", [p.stem for p in sorted(SAMPLES.glob("*.json"))])
def test_every_sample_builds_a_valid_report(name):
    report = build(name)
    assert len(report["ingredients"]) == len(json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))["ingredients"])


def test_regulatory_findings_carry_the_annex_text():
    report = build("leave_on_restricted")
    ing = {i["ingredient_id"]: i for i in report["ingredients"]}
    assert ing["zinc pyrithione"]["regulatory"]["status"] == "prohibited"
    assert ing["zinc pyrithione"]["regulatory"]["evidence_ids"] == ["eu_1223_2009_annex_ii#1670"]
    assert ing["methylisothiazolinone"]["regulatory"]["compliance_check"] == "not_satisfied"  # leave-on, rinse-off only
    sources = {s["evidence_id"]: s for s in report["sources"]}
    assert "Annex II" in sources["eu_1223_2009_annex_ii#1670"]["excerpt"]
    assert sources["regulatory_scope#aqua"]["kind"] == "coverage_list"
    assert report["overview"]["prohibited"] == 1 and report["overview"]["conditions_not_met"] == 1


def test_placeholder_quotes_are_replaced_by_the_clp_row_or_reported():
    report = build("sensitiser_claimed")
    clp = next(s for s in report["sources"] if s["evidence_id"] == "clp_test_ingredients#methylisothiazolinone")
    assert "Skin Sens. 1A" in clp["excerpt"] and "MOCK" not in clp["excerpt"]
    assert check(report, "excerpts_available")["passed"]


def test_fake_certification_fails_the_checks():
    req = chain("clean_product")
    fake = {"name": "Mock list", "source_id": "mock_certified_brands"}  # not in the corpus, placeholder text
    req["ethics"].update(status="VERIFIED", certifications_found=[fake], evidence=[
        {"type": "certification", "source": "Mock list", "detail": "MOCK - replace with retrieved text",
         "source_id": "mock_certified_brands"}])
    report = client.post("/report/build", json=req).json()
    assert report["cruelty_free"]["status"] == "verified"
    assert not check(report, "citations_known")["passed"]
    assert not check(report, "excerpts_available")["passed"]
    assert not report["validation"]["passed"]


def test_missing_agent_is_a_warning_not_an_error():
    req = chain("sensitiser_claimed")
    del req["ethics"]
    report = client.post("/report/build", json=req).json()
    assert report["cruelty_free"]["status"] == "not_assessed"
    assert not check(report, "agents_present")["passed"]
    assert report["validation"]["passed"]


def test_judged_concentration_limit_fails():
    req = chain("barcode_found")
    for f in req["regulatory"]["findings"]:
        for c in f["conditions"]:
            if c["type"] == "max_concentration":
                c["result"] = "satisfied"
    report = client.post("/report/build", json=req).json()
    assert not check(report, "missing_concentration")["passed"]


def test_verdict_wording_fails():
    req = chain("sensitiser_claimed")
    req["toxicology"]["findings"][0]["risk_interpretation"] = "This ingredient is toxic, avoid it."
    report = client.post("/report/build", json=req).json()
    assert not check(report, "no_safety_verdicts")["passed"]


# ---- validator on a built report ------------------------------------------------------


@pytest.fixture
def fake_model(monkeypatch):
    answers, calls = [], []

    def chat(messages, temperature=0.0, **kwargs):
        calls.append(messages)
        return answers.pop(0)

    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(llm, "model_name", lambda: "test-model")
    return answers, calls


def verdict(agent_name, ingredient_id, v="supported"):
    return {"agent": agent_name, "ingredient_id": ingredient_id, "claim": "x", "evidence_ids": [], "verdict": v, "reason": "r"}


def test_validator_sees_claims_with_text_and_the_product_type(fake_model):
    answers, calls = fake_model
    report = build("leave_on_restricted")
    answers.append(json.dumps({"valid": True, "claims": [verdict("regulatory", "zinc pyrithione")], "issues": []}))
    out = client.post("/report/validate", json={"report": report}).json()
    sent = calls[0][1]["content"]
    assert "eu_1223_2009_annex_ii#1670" in sent and "leave_on" in sent
    assert "regulatory_scope#aqua" not in sent  # negative findings are not sent
    assert out["status"] == "completed"


def test_invented_claims_are_ignored(fake_model):
    answers, _ = fake_model
    report = build("leave_on_restricted")  # cruelty-free not_verified: no cruelty-free claim to judge
    answers.append(json.dumps({"valid": False, "claims": [verdict("ethics", None, "unsupported")], "issues": ["x"]}))
    out = client.post("/report/validate", json={"report": report}).json()
    assert check(out["report"], "ai_validator")["passed"]


def test_flags_are_advisory_unless_blocking(fake_model, monkeypatch):
    answers, _ = fake_model
    report = build("leave_on_restricted")
    flag = json.dumps({"valid": False, "claims": [verdict("regulatory", "zinc pyrithione", "overstated")], "issues": []})
    answers.append(flag)
    out = client.post("/report/validate", json={"report": report}).json()
    ai = check(out["report"], "ai_validator")
    assert not ai["passed"] and ai["severity"] == "warning" and out["status"] == "completed"

    monkeypatch.setattr(agent, "BLOCKING", True)
    answers.append(flag)
    out = client.post("/report/validate", json={"report": report}).json()
    assert check(out["report"], "ai_validator")["severity"] == "error" and out["status"] == "needs_review"


def test_model_outage_does_not_block_the_report(monkeypatch):
    def down(*args, **kwargs):
        raise llm.LLMError("Model endpoint answered HTTP 503")

    monkeypatch.setattr(llm, "chat", down)
    out = client.post("/report/validate", json={"report": build("leave_on_restricted")}).json()
    ai = check(out["report"], "ai_validator")
    assert ai["severity"] == "warning" and "503" in ai["issues"][0]
    assert out["status"] == "completed" and out["validator"] is None
