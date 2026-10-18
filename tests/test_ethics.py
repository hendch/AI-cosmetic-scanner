import json
from pathlib import Path

import pytest

from app.common_schemas import ProductInput
from app.ethics.agent import analyze, load_peta, normalize, parse_peta

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PETA = parse_peta(json.loads((FIXTURES / "peta_brands.json").read_text(encoding="utf-8")))
PARENTS = {"balea": "dm-drogerie markt", "garnier": "L'Oréal", "goodie": "Good Parent"}


def run(brand: str, labels: list[str] | None = None, peta=PETA):
    payload = ProductInput(product={"brand": brand, "labels": labels or []}, ingredients=[])
    return analyze(payload, peta=peta, parents=PARENTS)


def test_normalize_matches_peta_spelling():
    assert normalize("L’Oréal") == normalize("L'Oreal") == "loreal"
    assert normalize("Good Parent GmbH") == "good parent"


def test_brand_on_dont_test_list_is_verified():
    r = run("Catrice")
    assert r.status == "VERIFIED" and r.evidence_confidence == "high"
    assert [c.source_id for c in r.certifications_found] == ["peta_beauty_without_bunnies"]
    assert r.certifications_checked == ["PETA Beauty Without Bunnies"]


def test_brand_listing_wins_over_parent_but_parent_is_reported():
    r = run("Urban Decay")
    assert r.status == "VERIFIED" and r.parent_company == "L’Oréal"
    assert any(e.type == "third_party_report" and "L’Oreal" in e.detail for e in r.evidence)


def test_brand_on_do_test_list_is_not_verified():
    r = run("NIVEA")
    assert r.status == "NOT_VERIFIED" and r.parent_company == "Beiersdorf"
    assert "test on animals" in r.status_reason


def test_cruelty_free_label_on_testing_brand_is_conflicting():
    r = run("Nivea", ["en:cruelty-free"])
    assert r.status == "CONFLICTING" and r.conflicts


def test_parent_from_mapping_decides_when_brand_not_listed():
    garnier = run("Garnier")  # L'Oréal tests
    assert garnier.status == "NOT_VERIFIED" and garnier.parent_company == "L'Oréal"
    goodie = run("Goodie")  # parent on the don't-test list
    assert goodie.status == "VERIFIED" and goodie.evidence_confidence == "medium"
    assert "brand-level certification" in goodie.missing_information


def test_unlisted_parent_is_named_but_not_verified():
    r = run("Balea")
    assert r.status == "NOT_VERIFIED" and r.parent_company == "dm-drogerie markt"
    assert "dm-drogerie markt" in r.status_reason


def test_label_without_listing_is_only_claimed():
    r = run("Unknown Brand", ["en:cruelty-free"])
    assert r.status == "CLAIMED" and any(e.type == "brand_claim" for e in r.evidence)


def test_multi_brand_field_is_split():
    assert run("Unknown Brand, Catrice").status == "VERIFIED"


def test_duplicate_listing_with_both_statuses_is_never_verified():
    assert run("Twice Listed").status == "NOT_VERIFIED"


def test_eu_ban_is_context_only():
    r = run("Unknown Brand")
    assert r.status == "NOT_VERIFIED"
    assert any(e.type == "regulatory" for e in r.evidence)


def test_missing_peta_list_is_reported(monkeypatch, tmp_path):
    monkeypatch.setenv("PETA_BRANDS_PATH", str(tmp_path / "absent.json"))
    payload = ProductInput(product={"brand": "Catrice"}, ingredients=[])
    r = analyze(payload, parents=PARENTS)
    assert load_peta() is None
    assert r.status == "NOT_VERIFIED" and r.certifications_checked == [] and r.evidence_confidence == "low"
    assert any("PETA brand list not available" in w for w in r.warnings)


@pytest.mark.parametrize("brand", ["", "   "])
def test_unknown_brand(brand):
    r = run(brand)
    assert r.status == "NOT_VERIFIED" and r.missing_information == ["brand"]
