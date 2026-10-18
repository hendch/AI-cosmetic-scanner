"""Live agent logic with a fake LLM: no network, no cost."""

import json
from pathlib import Path

from app.common_schemas import ProductInput
from app.regulatory.agent import analyze
from app.common.llm import parse_json_object
from app.regulatory.agent import load_prompt

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "input"


def _payload(name: str) -> ProductInput:
    return ProductInput.model_validate_json((SAMPLES / name).read_text(encoding="utf-8"))


def _conditions_in(messages: list[dict]) -> list[str]:
    user = messages[1]["content"]
    block = user.split("CONDITIONS TO CHECK:")[1].split("Return JSON")[0]
    return [line for line in block.strip().splitlines() if line.startswith("[")]


def _ids_in(messages: list[dict]) -> list[str]:
    return sorted({line.split("evidence_id: ")[1].split(" |")[0]
                   for line in messages[1]["content"].splitlines() if line.startswith("[evidence_id:")})


class FakeLLM:
    """Answers every condition with `result`, unless `answers` gives raw texts to return in order."""

    def __init__(self, result="unknown", answers=None, explanation="The entry sets conditions of use that cannot all be confirmed."):
        self.result, self.answers, self.explanation, self.calls = result, list(answers or []), explanation, []

    def __call__(self, messages, temperature, max_tokens):
        self.calls.append(messages)
        if self.answers:
            return self.answers.pop(0)
        conds = _conditions_in(messages)
        return json.dumps({
            "regulatory_status": "restricted",
            "conditions": [{"index": i, "result": self.result, "reason": "fake"} for i in range(len(conds))],
            "explanation": self.explanation,
            "missing_information": ["concentration"],
            "evidence_ids": _ids_in(messages),
        })


def _by_name(response):
    return {f.ingredient: f for f in response.findings}


def test_llm_is_called_only_for_restricted_ingredients():
    llm = FakeLLM()
    resp = analyze(_payload("leave_on_restricted.json"), chat=llm, prompt=load_prompt("v2"))
    # salicylic acid, retinol, methylisothiazolinone, sodium benzoate -> 4 calls; aqua, niacinamide, zinc pyrithione -> none
    assert len(llm.calls) == 4
    f = _by_name(resp)
    assert f["zinc pyrithione"].regulatory_status == "prohibited"
    assert f["niacinamide"].regulatory_status == "no_restriction_found"
    assert f["sodium benzoate"].regulatory_status == "restricted"  # Annex V/1, corpus extended 2026-10-18
    assert resp.run.mode == "live" and resp.run.llm_calls == 4 and resp.prompt_version == "v2"


def test_safety_rules_override_the_llm():
    llm = FakeLLM(result="satisfied")  # claims every condition is met
    resp = analyze(_payload("leave_on_restricted.json"), chat=llm, prompt=load_prompt("v2"))
    f = _by_name(resp)
    mi = f["methylisothiazolinone"]
    assert {c.type: c.result for c in mi.conditions}["product_type"] == "not_satisfied"  # leave-on: rule wins
    assert mi.compliance_check == "not_satisfied"
    for finding in resp.findings:
        for c in finding.conditions:
            if c.type in ("max_concentration", "labelling"):
                assert c.result == "unknown"
    assert resp.run.overrides


def test_label_warnings_are_never_decided_without_label_text():
    llm = FakeLLM(result="not_satisfied")  # claims the warning is missing from the label
    resp = analyze(_payload("leave_on_restricted.json"), chat=llm, prompt=load_prompt("v2"))
    retinol = _by_name(resp)["retinol"]
    assert {c.type: c.result for c in retinol.conditions}["labelling"] == "unknown"


def test_invalid_citation_triggers_retry_then_fallback():
    bad = json.dumps({"regulatory_status": "restricted", "conditions": [{"index": 0, "result": "unknown", "reason": "x"}],
                      "explanation": "Allowed up to 1 %.", "missing_information": [], "evidence_ids": ["made_up_source"]})
    llm = FakeLLM(answers=[bad, bad])
    resp = analyze(_payload("clean_product.json"), chat=llm, prompt=load_prompt("v2"))
    pe = _by_name(resp)["phenoxyethanol"]
    assert len(llm.calls) == 2 and resp.run.retries == 1 and resp.run.fallbacks == 1
    assert "Your answer was invalid" in llm.calls[1][-1]["content"]
    assert pe.sources == ["eu_1223_2009_annex_v"]  # conservative baseline keeps the real citation
    assert any("conservative result used" in w for w in resp.warnings)


def test_forbidden_wording_is_retried():
    llm = FakeLLM(explanation="Phenoxyethanol is safe at this level.")
    resp = analyze(_payload("clean_product.json"), chat=llm, prompt=load_prompt("v2"))
    assert resp.run.retries == 1 and resp.run.fallbacks == 1
    assert "safe" not in _by_name(resp)["phenoxyethanol"].explanation.lower()


def test_llm_failure_falls_back_without_crashing():
    def broken(messages, temperature, max_tokens):
        raise ConnectionError("no network")

    resp = analyze(_payload("sensitiser_claimed.json"), chat=broken, prompt=load_prompt("v2"))
    mi = _by_name(resp)["methylisothiazolinone"]
    assert mi.regulatory_status == "restricted" and mi.compliance_check == "unknown"
    assert any("LLM call failed" in w for w in resp.warnings)


def test_http_retrieval_without_url_reports_missing_evidence(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_BACKEND", "http")
    monkeypatch.delenv("RETRIEVAL_URL", raising=False)
    resp = analyze(_payload("clean_product.json"), chat=FakeLLM(), prompt=load_prompt("v2"))
    assert _by_name(resp)["phenoxyethanol"].regulatory_status == "not_assessed"
    assert any("RETRIEVAL_URL" in w for w in resp.warnings)


def test_both_prompt_versions_render():
    for version in ("v1", "v2", "v3", "v4"):
        p = load_prompt(version)
        msgs = p.render(product="{}", ingredient="x", concentration="unknown", status="restricted",
                        evidence="e", conditions="[0] c", output_schema="{}")
        assert "{" + "evidence" + "}" not in msgs[1]["content"]


def test_parse_json_tolerates_fences_and_chatter():
    text = 'Sure! ```json\n{"a": "x \\" }", "b": [1, {"c": 2}]}\n``` done'
    assert parse_json_object(text) == {"a": 'x " }', "b": [1, {"c": 2}]}


def test_skipped_condition_decided_by_rule_is_filled_without_retry():
    # Real Qwen behaviour: it skips the concentration condition when it is obviously unknown.
    answer = json.dumps({"regulatory_status": "restricted",
                         "conditions": [{"index": 0, "result": "satisfied", "reason": "rinse-off shampoo"}],
                         "explanation": "Annex V entry 57 allows it in rinse-off products up to 0,0015 %.",
                         "missing_information": ["concentration"], "evidence_ids": ["eu_1223_2009_annex_v"]})
    llm = FakeLLM(answers=[answer])
    resp = analyze(_payload("sensitiser_claimed.json"), chat=llm, prompt=load_prompt("v3"))
    mi = _by_name(resp)["methylisothiazolinone"]
    assert resp.run.retries == 0 and len(llm.calls) == 1
    assert [c.result for c in mi.conditions] == ["satisfied", "unknown"]


def test_replay_of_recorded_qwen_answers():
    from scripts.replay_regulatory import main

    results = main()
    cream = {f["ingredient"]: f for f in results["leave_on_restricted"]["findings"]}
    assert cream["methylisothiazolinone"]["compliance_check"] == "not_satisfied"
    assert cream["salicylic acid"]["conditions"][0]["result"] == "satisfied"  # item (b) matched by rule
    # The recorded answers predate sodium benzoate's corpus entry (V/1): no answer for it, so it falls
    # back to the rule-based result. Every other ingredient replays without fallback.
    assert results["leave_on_restricted"]["run"]["fallbacks"] == 1
    assert cream["sodium benzoate"]["regulatory_status"] == "restricted"
    assert all(r["run"]["fallbacks"] == 0 for name, r in results.items() if name != "leave_on_restricted")


def test_missing_token_falls_back_to_rules(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://router.huggingface.co/v1")
    resp = analyze(_payload("leave_on_restricted.json"))  # no chat given, no token: used to raise (HTTP 500)
    assert resp.run is None or resp.run.mode == "mock"
    assert any("LLM unavailable" in w for w in resp.warnings)
    assert _by_name(resp)["zinc pyrithione"].regulatory_status == "prohibited"


# ---- retrieval backends (RAG adapter) ---------------------------------------------------

def test_rag_results_keep_only_annex_entries():
    from app.regulatory.retrieval import _from_rag

    items = [
        {"evidence_id": "eu_1223_2009_annex_v#29", "text": "Annex V, entry 29", "score": 0.9,
         "metadata": {"doc_type": "regulation", "annex": "V", "entry": "29", "source_id": "eu_1223_2009_annex_v",
                      "ingredients": "phenoxyethanol", "max_concentration": "1,0 %"}},
        {"evidence_id": "EV-PHENOXYETHANOL-SCCS-OVERALL", "text": "SCCS opinion", "score": 0.8,
         "metadata": {"source_id": "sccs_phenoxyethanol"}},  # not an annex entry: dropped
    ]
    passages = _from_rag(items)
    assert [(p.annex, p.entry, p.source_id) for p in passages] == [("V", "29", "eu_1223_2009_annex_v")]
    assert passages[0].to_row().max_concentration == "1,0 %"


def test_http_backend_calls_the_rag_route_with_the_key(monkeypatch):
    from app.regulatory import retrieval

    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"evidence_id": "eu_1223_2009_annex_ii#1670", "text": "Annex II", "score": 1.0,
                                 "metadata": {"doc_type": "regulation", "annex": "II", "entry": "1670",
                                              "source_id": "eu_1223_2009_annex_ii", "ingredients": "zinc pyrithione"}}]}

    def post(url, json, headers, timeout):
        seen.update(url=url, body=json, headers=headers)
        return Resp()

    monkeypatch.setattr(retrieval.httpx, "post", post)
    monkeypatch.setenv("RETRIEVAL_BACKEND", "http")
    monkeypatch.setenv("RETRIEVAL_URL", "https://api.example")
    monkeypatch.setenv("SCANNER_API_KEY", "k")
    passages = retrieval.search_regulation("zinc pyrithione")
    assert seen["url"] == "https://api.example/rag/retrieve" and seen["headers"]["X-API-Key"] == "k"
    assert seen["body"]["ingredient"] == "zinc pyrithione" and seen["body"]["strategy"] == "structured"
    assert [p.entry for p in passages] == ["1670"]
