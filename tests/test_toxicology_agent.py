"""Toxicology agent on the shipped index (local backend, fake model: no credits)."""

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.common_schemas import ProductInput
from app.main import app
from app.toxicology import agent as tox_agent
from app.toxicology import rules
from app.toxicology.agent import analyze, load_prompt
from app.toxicology.retrieval import SCCS, _shipped, search_toxicology

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def payload(*names: str, confidence: float = 1.0) -> ProductInput:
    return ProductInput(product={"name": "Test cream", "category": "face cream", "exposure_type": "leave_on"},
                        ingredients=[{"position": i + 1, "raw": n, "normalized": n, "matched": True,
                                      "confidence": confidence} for i, n in enumerate(names)])


def by_name(resp):
    return {f.ingredient: f for f in resp.findings}


class FakeLLM:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, messages, temperature, max_tokens):
        self.calls.append(messages)
        return self.answers.pop(0) if self.answers else self.answers_last

    @property
    def answers_last(self):
        raise AssertionError("unexpected extra LLM call")


def conclusion(ingredient: str):
    p = next(p for p in search_toxicology(ingredient) if p.doc_type == SCCS)
    sentence = next(s.strip() for s in p.text.replace("\n", " ").split(". ") if len(s.split()) > 8)
    return p, sentence


def answer(evidence_id, quote, interpretation="The SCCS accepted its use as a preservative; "
                                              "the concentration in this product is not given.", endpoint="other"):
    return json.dumps({"sccs_findings": [{"endpoint": endpoint, "finding": "Assessed as a preservative",
                                          "evidence_id": evidence_id, "quote": quote}],
                       "risk_interpretation": interpretation, "missing_information": ["concentration"],
                       "evidence_ids": [evidence_id]})


# ---- the index ----------------------------------------------------------------------------
def test_index_holds_sccs_and_clp_passages_with_registered_sources():
    with (ROOT / "corpus" / "sources.csv").open(encoding="utf-8") as f:
        known = {r["source_id"] for r in csv.DictReader(f)}
    kinds = {p["doc_type"] for p in _shipped()}
    assert kinds == {"clp", "sccs_opinion"}
    assert {p["source_id"] for p in _shipped()} <= known  # the report accepts every citation
    sections = {p["section"] for p in _shipped() if p["source_id"] == "sccs_phenoxyethanol_2016"}
    assert "Conclusion" in sections


# ---- rules mode ---------------------------------------------------------------------------
def test_clp_hazards_and_concern_levels_come_from_the_retrieved_clp_passage():
    f = by_name(analyze(payload("methylisothiazolinone", "zinc pyrithione", "retinol", "glycerin", "bht"), mode="rules"))
    mi = f["methylisothiazolinone"]
    assert "CLP Skin Sens. 1A (H317)" in [h.classification for h in mi.hazards]
    assert mi.concern_level == "moderate" and mi.evidence_confidence == "high"
    assert all("Skin Sens. 1A" in h.quote for h in mi.hazards)  # real text, not a placeholder
    assert f["zinc pyrithione"].concern_level == "high"  # harmonised Repr. 1B
    assert f["retinol"].concern_level == "moderate"  # Repr. 1B notified only, not harmonised
    assert f["glycerin"].concern_level == "none_identified"
    assert f["bht"].concern_level == "none_identified" and not f["bht"].hazards  # aquatic only: not consumer health


def test_sources_cite_the_sccs_opinion_and_rules_mode_makes_no_llm_call():
    resp = analyze(payload("phenoxyethanol"), mode="rules", chat=FakeLLM([]))
    pe = by_name(resp)["phenoxyethanol"]
    assert pe.sources == ["clp_test_ingredients", "sccs_phenoxyethanol_2016"]
    assert resp.run.mode == "rules" and resp.run.llm_calls == 0 and resp.prompt_version == "rules"


def test_ingredient_outside_the_corpus_is_insufficient_evidence(monkeypatch):
    monkeypatch.setattr("app.toxicology.retrieval._local_search", lambda *a: pytest.fail("no search expected"))
    f = by_name(analyze(payload("allantoin"), mode="rules"))["allantoin"]
    assert f.concern_level == "insufficient_evidence" and f.sources == []


def test_ocr_confidence_lowers_evidence_confidence():
    f = by_name(analyze(payload("phenoxyethanol", confidence=0.6), mode="rules"))["phenoxyethanol"]
    assert f.evidence_confidence == "low" and "ingredient name from OCR, unverified" in f.missing_information


# ---- live mode (fake model) ---------------------------------------------------------------
def test_valid_sccs_finding_is_added_with_its_quote():
    p, quote = conclusion("phenoxyethanol")
    llm = FakeLLM([answer(p.evidence_id, quote)])
    resp = analyze(payload("phenoxyethanol"), chat=llm, prompt=load_prompt("v2"))
    pe = by_name(resp)["phenoxyethanol"]
    sccs = [h for h in pe.hazards if h.source_id == "sccs_phenoxyethanol_2016"]
    assert len(sccs) == 1 and sccs[0].quote == quote and sccs[0].classification.startswith("SCCS: ")
    assert pe.risk_interpretation.startswith("The SCCS accepted")
    assert resp.run.llm_calls == 1 and resp.run.retries == 0 and resp.prompt_version == "v2"
    assert p.evidence_id in llm.calls[0][1]["content"]  # the model saw the retrieved passage


def test_invented_quote_is_dropped():
    p, _ = conclusion("phenoxyethanol")
    invented = answer(p.evidence_id, "the SCCS found it causes nothing at all")
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([invented, invented]), prompt=load_prompt("v2"))
    pe = by_name(resp)["phenoxyethanol"]
    assert all(h.source_id == "clp_test_ingredients" for h in pe.hazards)
    assert resp.run.rejected_findings[0].startswith("phenoxyethanol (attempt 1): ")
    assert "word for word" in resp.run.rejected_findings[0]
    assert pe.risk_interpretation.startswith("CLP harmonised")  # its text had nothing behind it: rule text


def test_verdict_wording_is_retried_then_falls_back_to_rules():
    p, quote = conclusion("phenoxyethanol")
    bad = answer(p.evidence_id, quote, interpretation="Phenoxyethanol is safe at this level.")
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([bad, bad]), prompt=load_prompt("v2"))
    pe = by_name(resp)["phenoxyethanol"]
    assert resp.run.retries == 1 and resp.run.fallbacks == 1
    assert pe.risk_interpretation.startswith("CLP harmonised")  # the rule text
    assert [i.split(":")[0] for i in resp.run.llm_issues] == ["phenoxyethanol (attempt 1)", "phenoxyethanol (attempt 2)"]
    assert "forbidden word(s) ['safe']" in resp.run.llm_issues[0]


def test_a_string_where_a_list_is_expected_is_accepted():
    p, quote = conclusion("phenoxyethanol")
    raw = json.loads(answer(p.evidence_id, quote))
    raw["missing_information"] = "concentration"  # real Qwen 7B answer shape
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([json.dumps(raw)]), prompt=load_prompt("v4"))
    assert resp.run.retries == 0 and resp.run.fallbacks == 0


def test_schema_errors_name_the_field():
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM(['{"risk_interpretation": "x"}', "not json"]),
                   prompt=load_prompt("v2"))
    assert "evidence_ids: Field required" in resp.run.llm_issues[0]
    assert "answer starts: 'not json'" in resp.run.llm_issues[1]


def pe_conclusion_sentence():
    """The phenoxyethanol conclusion passage and its 1.0 % sentence, as retrieved."""
    import re
    p = next(p for p in search_toxicology("phenoxyethanol") if p.evidence_id.endswith("conclusion-000"))
    text = " ".join(p.text.split())
    return p, re.search(r"The SCCS considers 2-phenoxyethanol safe[^.]*?1\.0%[^.]*\.", text).group(0)


def findings_answer(*findings):
    return json.dumps({"sccs_findings": [{"endpoint": "other", "finding": label, "evidence_id": eid, "quote": quote}
                                         for label, eid, quote in findings],
                       "risk_interpretation": "The SCCS raised no concern up to 1.0 % as a preservative.",
                       "missing_information": ["concentration"], "evidence_ids": [findings[0][1]]})


@pytest.mark.parametrize("label, reason", [
    ("Use in leave-on face cream not supported by the SCCS", "label names ['leave-on', 'face']"),  # real v6 failure
    ("No SCCS concern up to 2 %", "label quantity ['2 %'] not in the quote"),  # quote has "2-phenoxyethanol", not "2 %"
    ("No SCCS concern up to 1.0 % in hair products", "label names ['hair']"),
])
def test_label_must_say_what_its_quote_says(label, reason):
    p, sentence = pe_conclusion_sentence()
    wrong = findings_answer((label, p.evidence_id, sentence))
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([wrong, wrong]), prompt=load_prompt("v6"))
    assert not [h for h in by_name(resp)["phenoxyethanol"].hazards if h.source_id.startswith("sccs")]
    assert reason in resp.run.rejected_findings[0]


def test_same_quantity_written_differently_is_accepted():
    p, sentence = pe_conclusion_sentence()  # "... maximum concentration of 1.0%, ..."
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([findings_answer(("No SCCS concern up to 1 %", p.evidence_id, sentence))]),
                   prompt=load_prompt("v6"))
    assert resp.run.rejected_findings == []


def test_a_wrong_first_finding_does_not_push_out_a_correct_second_one():
    p, sentence = pe_conclusion_sentence()
    wrong = ("Use in leave-on face cream not supported by the SCCS", p.evidence_id, sentence)
    right = ("No SCCS concern up to 1.0% as a preservative", p.evidence_id, sentence)
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([findings_answer(wrong, right)]), prompt=load_prompt("v6"))
    sccs = [h for h in by_name(resp)["phenoxyethanol"].hazards if h.source_id.startswith("sccs")]
    assert [h.classification for h in sccs] == ["SCCS: No SCCS concern up to 1.0% as a preservative"]


def test_all_findings_rejected_is_retried_with_the_reason():
    # Real v6 run (octocrylene, propylparaben): the label was rejected but its text was kept, unsupported.
    p, sentence = pe_conclusion_sentence()
    wrong = findings_answer(("No SCCS concern up to 1.0 % in sunscreen body lotion", p.evidence_id, sentence))
    right = findings_answer(("No SCCS concern up to 1.0% as a preservative", p.evidence_id, sentence))
    llm = FakeLLM([wrong, right])
    resp = analyze(payload("phenoxyethanol"), chat=llm, prompt=load_prompt("v6"))
    retry = llm.calls[1][-1]["content"]
    assert "every sccs_finding was rejected" in retry and "label names ['body', 'sunscreen']" in retry
    sccs = [h for h in by_name(resp)["phenoxyethanol"].hazards if h.source_id.startswith("sccs")]
    assert [h.classification for h in sccs] == ["SCCS: No SCCS concern up to 1.0% as a preservative"]
    assert resp.run.retries == 1 and resp.run.fallbacks == 0


def test_interpretation_numbers_must_come_from_an_accepted_quote():
    p, sentence = pe_conclusion_sentence()
    raw = json.loads(findings_answer(("No SCCS concern up to 1.0% as a preservative", p.evidence_id, sentence)))
    raw["risk_interpretation"] = "The SCCS raised no concern up to 10% in sunscreen lotion."
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([json.dumps(raw)] * 2), prompt=load_prompt("v6"))
    assert "risk_interpretation gives ['10 %']" in resp.run.llm_issues[0]
    assert resp.run.fallbacks == 1 and "10%" not in by_name(resp)["phenoxyethanol"].risk_interpretation


def test_interpretation_may_give_the_labelled_concentration():
    p, sentence = pe_conclusion_sentence()
    raw = json.loads(findings_answer(("No SCCS concern up to 1.0% as a preservative", p.evidence_id, sentence)))
    raw["risk_interpretation"] = "This product contains 0.8 %, below the 1.0 % the SCCS assessed."
    body = payload("phenoxyethanol")
    body.ingredients[0].concentration_percent = 0.8
    resp = analyze(body, chat=FakeLLM([json.dumps(raw)]), prompt=load_prompt("v6"))
    assert resp.run.retries == 0 and resp.run.llm_issues == []


@pytest.mark.parametrize("quote, concern", [
    ("The use of BP-3 as a UV-filter up to a maximum concentration of 6% in sunscreen products, either in the "
     "form of body cream, sunscreen propellant spray or pump spray, is not safe for the consumer.", True),
    ("The information provided does not support the safe use of MI as a preservative in leave-on hair cosmetic "
     "products up to a concentration limit of 100 ppm", True),
    ("However, the use of Octocrylene at 10% or above in sunscreen propellant spray is not considered safe", True),
    ("The SCCS considers 2-phenoxyethanol safe for use as a preservative with a maximum concentration of 1.0%", False),
    ("this Opinion is not applicable to any sprayable product (including mouth spray)", False),  # scope, not concern
    ("adequate evidence has not been provided for the safe use of propyl- or butylparaben in cosmetics.", True),
    ("The results of the recent Scandinavian study do not support safety of MI in rinse-off products", True),
    ("there are a number of uncertainties and data gaps that do not allow a conclusion on the safety of "
     "titanium dioxide (nano)", False),  # inconclusive, not a concern
])
def test_sccs_concern_is_read_from_the_quote(quote, concern):
    assert rules.sccs_concern(quote) is concern


def bp3_not_safe_sentence():
    """BP-3: "... 6% in sunscreen products, either in the form of body cream, ... is not safe for the consumer." """
    quote = "is not safe for the consumer"
    p = next(p for p in search_toxicology("benzophenone-3", top_k=8) if quote in " ".join(p.text.split()))
    sentence = next(s for s in " ".join(p.text.split()).split(". ") if quote in s)
    return p, sentence[sentence.index("The use of BP-3"):]


def labelled(label, p, sentence, interpretation):
    raw = json.loads(findings_answer((label, p.evidence_id, sentence)))
    raw["risk_interpretation"] = interpretation
    return json.dumps(raw)


def test_sccs_not_safe_quote_raises_the_concern_level():
    # Real v6 run: BP-3 "not safe for the consumer" in sunscreen body cream came out as "low".
    p, sentence = bp3_not_safe_sentence()
    llm = FakeLLM([labelled("Use in sunscreen products not supported by the SCCS", p, sentence,
                            "The SCCS raised a concern for use as a UV-filter up to 6% in sunscreen products.")])
    resp = analyze(payload("benzophenone-3"), chat=llm, prompt=load_prompt("v6"))
    bp3 = by_name(resp)["benzophenone-3"]
    assert resp.run.rejected_findings == [] and bp3.concern_level == "moderate"


@pytest.mark.parametrize("label, reworded", [
    ("Not safe in sunscreen products up to 6%", "SCCS: SCCS concern in sunscreen products up to 6%"),  # real v7 label
    ("Unsafe in sunscreen products up to 6%", "SCCS: SCCS concern in sunscreen products up to 6%"),
])
def test_label_opening_with_the_verdict_is_reworded_not_rejected(label, reworded):
    # v7: BP-3 fell back twice on this label and lost its "not safe for the consumer" conclusion.
    p, sentence = bp3_not_safe_sentence()
    llm = FakeLLM([labelled(label, p, sentence,
                            "The SCCS raised a concern for use up to 6% in sunscreen products.")])
    resp = analyze(payload("benzophenone-3"), chat=llm, prompt=load_prompt("v7"))
    bp3 = by_name(resp)["benzophenone-3"]
    assert [h.classification for h in bp3.hazards if h.source_id.startswith("sccs")] == [reworded]
    assert bp3.concern_level == "moderate" and resp.run.retries == 0
    assert "label reworded" in resp.run.llm_issues[0]  # still visible when comparing prompt versions


def test_safe_label_is_reworded_to_no_concern():
    p, sentence = pe_conclusion_sentence()
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([findings_answer(("Safe up to 1.0% in cosmetic products",
                                                                             p.evidence_id, sentence))]),
                   prompt=load_prompt("v7"))
    sccs = [h for h in by_name(resp)["phenoxyethanol"].hazards if h.source_id.startswith("sccs")]
    assert [h.classification for h in sccs] == ["SCCS: No SCCS concern up to 1.0% in cosmetic products"]


@pytest.mark.parametrize("which, label, reason", [
    ("bp3", "Safe up to 6% in sunscreen products", "label says no concern, the quote states a concern"),
    ("pe", "SCCS concern for use up to 1.0%", "label states a concern, the quote does not"),  # real v6 propylparaben retry
])
def test_label_must_agree_with_the_quote_on_concern(which, label, reason):
    p, sentence = bp3_not_safe_sentence() if which == "bp3" else pe_conclusion_sentence()
    name = "benzophenone-3" if which == "bp3" else "phenoxyethanol"
    wrong = labelled(label, p, sentence, "The SCCS opinion is cited.")
    resp = analyze(payload(name), chat=FakeLLM([wrong, wrong]), prompt=load_prompt("v7"))
    assert reason in resp.run.rejected_findings[0]


def test_no_concern_conclusion_does_not_raise_the_level():
    # v7 run: propylparaben (no CLP health classification) went to "low" on "no concern up to 0.14 %".
    p = next(p for p in search_toxicology("propylparaben", top_k=8) if "0.14 %" in " ".join(p.text.split()))
    text = " ".join(p.text.split())
    sentence = next(s.strip() for s in text.split("? ") if "has concluded that" in s and "0.14 %" in s)
    sentence = sentence[sentence.index("On the basis"):]
    llm = FakeLLM([labelled("No SCCS concern up to 0.14 % in cosmetic products", p, sentence,
                            "The SCCS raised no concern up to 0.14 % in cosmetic products.")])
    resp = analyze(payload("propylparaben"), chat=llm, prompt=load_prompt("v7"))
    pp = by_name(resp)["propylparaben"]
    assert resp.run.rejected_findings == [] and len(pp.hazards) == 1
    assert pp.concern_level == "none_identified"


def test_quote_across_list_bullets_is_word_for_word():
    # v7: the salicylic acid 2.0 % quote was rejected twice; the PDF has "-" bullets on their own lines.
    p = next(p for p in search_toxicology("salicylic acid") if "up to 2.0 % for other products" in " ".join(p.text.split()))
    assert "\n- \nup to 2.0 %" in p.text  # the layout this test is about
    quote = ("is safe at a concentration: up to 3.0 % for the cosmetic rinse-off hair products, "
             "up to 2.0% for other products, except body lotion, eye shadow, mascara, eyeliner, lipstick, non-spray deodorant")
    llm = FakeLLM([labelled("No SCCS concern up to 2.0 % for other products", p, quote,
                            "The SCCS raised no concern up to 2.0 % for other products, which includes a face cream.")])
    resp = analyze(payload("salicylic acid"), chat=llm, prompt=load_prompt("v7"))
    assert resp.run.rejected_findings == [] and resp.run.retries == 0


def test_label_ending_with_the_verdict_is_reworded():
    # v7: zinc pyrithione "Use in rinse-off hair products up to 1% safe" was rejected, then flipped on retry.
    p, sentence = pe_conclusion_sentence()
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([findings_answer(("Use as a preservative up to 1.0% safe",
                                                                             p.evidence_id, sentence))]),
                   prompt=load_prompt("v7"))
    sccs = [h for h in by_name(resp)["phenoxyethanol"].hazards if h.source_id.startswith("sccs")]
    assert [h.classification for h in sccs] == ["SCCS: No SCCS concern: use as a preservative up to 1.0%"]


def test_findings_are_kept_when_only_the_text_fails_twice():
    # v7: salicylic acid's valid 0.5 % finding was lost because its text cited a rejected 2 %.
    p, sentence = pe_conclusion_sentence()
    bad_text = labelled("No SCCS concern up to 1.0% as a preservative", p, sentence,
                        "The SCCS raised no concern up to 1.0 %, and up to 2 % in face creams.")
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([bad_text, bad_text]), prompt=load_prompt("v7"))
    pe = by_name(resp)["phenoxyethanol"]
    assert [h.classification for h in pe.hazards if h.source_id.startswith("sccs")] == \
        ["SCCS: No SCCS concern up to 1.0% as a preservative"]
    assert pe.risk_interpretation.startswith("CLP harmonised") and "2 %" not in pe.risk_interpretation
    assert pe.risk_interpretation.endswith("SCCS findings: No SCCS concern up to 1.0% as a preservative.")
    assert resp.run.fallbacks == 1 and any("validated SCCS findings kept" in w for w in resp.warnings)


def test_rejected_quote_is_logged_with_its_start():
    p, _ = conclusion("phenoxyethanol")
    invented = answer(p.evidence_id, "the SCCS found it causes nothing at all")
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([invented, invented]), prompt=load_prompt("v7"))
    assert "quote starts 'the SCCS found it causes nothing at all'" in resp.run.rejected_findings[0]


def test_two_valid_findings_from_one_opinion_keep_the_first():
    p, sentence = pe_conclusion_sentence()
    first = ("No SCCS concern up to 1.0% as a preservative", p.evidence_id, sentence)
    second = ("Assessed as a preservative", p.evidence_id, sentence)
    resp = analyze(payload("phenoxyethanol"), chat=FakeLLM([findings_answer(first, second)]), prompt=load_prompt("v6"))
    assert "second valid finding from the same opinion" in resp.run.rejected_findings[0]


def test_llm_cannot_lower_the_concern_level():
    p, quote = conclusion("zinc pyrithione")
    resp = analyze(payload("zinc pyrithione"), chat=FakeLLM([answer(p.evidence_id, quote, endpoint="other")]),
                   prompt=load_prompt("v3"))
    assert by_name(resp)["zinc pyrithione"].concern_level == "high"


def test_llm_failure_keeps_the_rule_result():
    def broken(messages, temperature, max_tokens):
        raise ConnectionError("no network")

    resp = analyze(payload("methylisothiazolinone"), chat=broken, prompt=load_prompt("v2"))
    assert by_name(resp)["methylisothiazolinone"].concern_level == "moderate"
    assert resp.run.fallbacks == 1 and any("LLM call failed" in w for w in resp.warnings)


def test_clp_only_ingredient_needs_no_llm_call():
    resp = analyze(payload("glycerin"), chat=FakeLLM([]), prompt=load_prompt("v2"))
    assert resp.run.llm_calls == 0


@pytest.mark.parametrize("version", ["v4", "v5", "v6", "v7"])  # v2/v3 had the schema in the system message (known_failures)
def test_prompt_shows_the_model_the_schema_and_no_placeholder_is_left(version):
    p = search_toxicology("phenoxyethanol")
    messages = load_prompt(version).render(**tox_agent._fields(payload("phenoxyethanol").ingredients[0],
                                                               payload().product,
                                                               analyze(payload("phenoxyethanol"), mode="rules").findings[0], p))
    text = "\n".join(m["content"] for m in messages)
    assert '"sccs_findings"' in messages[1]["content"]
    for field in ("{output_schema}", "{evidence}", "{product}", "{ingredient}", "{clp}", "{concentration}"):
        assert field not in text


# ---- endpoint -----------------------------------------------------------------------------
def test_prompt_version_is_chosen_per_request(monkeypatch):
    monkeypatch.setenv("TOXICOLOGY_MODE", "live")
    p, quote = conclusion("phenoxyethanol")
    monkeypatch.setattr(tox_agent, "chat_function", lambda: FakeLLM([answer(p.evidence_id, quote)]))
    body = payload("phenoxyethanol").model_dump()
    assert client.post("/toxicology/analyze?prompt_version=v3", json=body).json()["prompt_version"] == "v3"
    assert client.post("/toxicology/analyze?prompt_version=v99", json=body).status_code == 400
