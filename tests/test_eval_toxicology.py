"""scripts/eval_toxicology.py: replay and scoring on recorded answers (no LLM)."""

import json

from app.toxicology.retrieval import search_toxicology
from scripts.eval_toxicology import NOT_COVERED, evaluate


def bht_answer(label: str) -> str:
    p = next(p for p in search_toxicology("bht") if "0.1% in toothpaste" in " ".join(p.text.split()))
    text = " ".join(p.text.split())
    quote = text[text.index("the SCCS is of the opinion that BHT is safe as an ingredient up to a maximum concentration "
                            "of 0.001% in mouthwash and 0.1% in toothpaste."):].split(". ")[0] + "."
    return json.dumps({"sccs_findings": [{"endpoint": "other", "finding": label, "evidence_id": p.evidence_id, "quote": quote}],
                       "risk_interpretation": "The SCCS raised no concern up to 0.1% in toothpaste. This covers this "
                                              "product. The risk depends on the concentration, which is not given.",
                       "missing_information": ["concentration"], "evidence_ids": [p.evidence_id]})


def test_replay_scores_recorded_answers_and_counts_missing_calls():
    recording = {"prompt_version": "v7", "raw_answers": [
        {"case": "regulatory/toothpaste", "ingredient": "bht", "text": bht_answer("No SCCS concern up to 0.1% in toothpaste")}]}
    r = evaluate("replay", "v7", cases="toothpaste", replay=recording)
    assert r["finding_recall"] == 50.0  # bht right; salicylic acid had no recorded answer
    assert r["finding_precision"] == 100.0 and r["concern_accuracy"] == 100.0
    assert r["replay_missing"] == 1 and r["fallbacks"] == 1


def test_a_limit_for_another_product_type_is_an_error():
    recording = {"prompt_version": "v7", "raw_answers": [
        {"case": "regulatory/toothpaste", "ingredient": "bht", "text": bht_answer("No SCCS concern up to 0.001% in mouthwash")}]}
    r = evaluate("replay", "v7", cases="toothpaste", replay=recording)
    assert r["finding_precision"] == 0.0
    assert any("limit ['0.001 %'] not in ['0.1 %']" in e for e in r["errors"])


def test_coverage_wording():
    # real v7 interpretations
    assert NOT_COVERED.search("This does not cover the use in sunscreen body lotion.")
    assert NOT_COVERED.search("This covers leave-on hair products but not face creams.")
    assert not NOT_COVERED.search("This covers the use in sunscreen body lotion, but the risk depends on the concentration.")
    assert not NOT_COVERED.search("This covers face cream only if its concentration is within this limit.")
