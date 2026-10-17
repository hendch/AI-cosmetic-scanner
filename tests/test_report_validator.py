"""Validator agent tests with a fake model: no network, no credits."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.report import agent, llm
from app.report.router import router
from app.report.schemas import Draft, ValidatorOutput

CASES = json.loads((Path(__file__).resolve().parent.parent / "evaluation" / "validator" / "cases.json").read_text(encoding="utf-8"))
DRAFT = Draft.model_validate(CASES[0]["draft"])

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def claim(verdict="supported", agent_name="toxicology"):
    return {"agent": agent_name, "ingredient_id": "phenoxyethanol", "claim": "x", "evidence_ids": [], "verdict": verdict, "reason": ""}


@pytest.fixture
def fake_model(monkeypatch):
    """Replaces the model with a queue of canned answers and records the messages sent."""
    answers, calls = [], []

    def chat(messages, temperature=0.0, timeout=90.0):
        calls.append({"messages": messages, "temperature": temperature})
        return answers.pop(0)

    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(llm, "model_name", lambda: "test-model")
    return answers, calls


def test_reads_fenced_json_and_sends_draft_at_temperature_zero(fake_model):
    answers, calls = fake_model
    answers.append('```json\n{"valid": true, "claims": [], "issues": []}\n```')
    response = agent.validate_draft(DRAFT, "v4")
    assert response.result.valid and response.attempts == 1
    assert calls[0]["temperature"] == 0
    assert "sccs_phenoxyethanol_2016#background" in calls[0]["messages"][1]["content"]


def test_retries_once_with_the_schema_error(fake_model):
    answers, calls = fake_model
    answers += ['{"valid": "maybe"}', json.dumps({"valid": True, "claims": [claim()], "issues": []})]
    response = agent.validate_draft(DRAFT, "v4")
    assert response.attempts == 2
    assert "did not match the required JSON schema" in calls[1]["messages"][-1]["content"]


def test_gives_up_after_two_bad_answers(fake_model):
    answers, _ = fake_model
    answers += ["not json", "still not json"]
    with pytest.raises(agent.ValidatorError, match="after 2 attempts"):
        agent.validate_draft(DRAFT, "v4")


def test_validity_comes_from_the_verdicts_not_the_models_flag():
    # Observed with v4: every claim supported, but the model answered valid=false.
    assert ValidatorOutput.model_validate({"valid": False, "claims": [claim()], "issues": []}).valid is True
    assert ValidatorOutput.model_validate({"valid": True, "claims": [claim("overstated")], "issues": []}).valid is False
    # v1 has no claims, so its own flag stands.
    assert ValidatorOutput.model_validate({"valid": True, "issues": []}).valid is True


def test_cruelty_free_is_accepted_as_the_ethics_agent():
    out = ValidatorOutput.model_validate({"valid": True, "claims": [claim(agent_name="cruelty_free")], "issues": []})
    assert out.claims[0].agent == "ethics"


def test_endpoint_returns_502_when_the_model_is_unreachable(monkeypatch):
    def down(*args, **kwargs):
        raise llm.LLMError("Model endpoint answered HTTP 503")

    monkeypatch.setattr(llm, "chat", down)
    response = client.post("/report/validate", json={"draft": CASES[0]["draft"]})
    assert response.status_code == 502
    assert "503" in response.json()["detail"]


@pytest.mark.parametrize("version", ["v1", "v2", "v3", "v4"])
def test_every_prompt_version_loads(version):
    prompt = agent.load_prompt(version)
    assert "{draft}" in prompt["user"] and prompt["model_params"]["temperature"] == 0
