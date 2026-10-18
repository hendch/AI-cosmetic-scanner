"""Ingredient normalization against the INCI dictionary (app/ingestion/data/inci_dictionary.json.gz)."""

import pytest

from app.ingestion.normalize import normalize, normalize_list, split_ingredients


@pytest.mark.parametrize("raw, expected", [
    ("Aqua", "aqua"), ("Water", "aqua"), ("Aqua/Water/Eau", "aqua"), ("Glycerin", "glycerin"),
    ("Glycerol", "glycerin"), ("Parfum (Fragrance)", "parfum"), ("Sodium Benzoate", "sodium benzoate"),
    ("Titanium Dioxide (CI 77891)", "titanium dioxide"), ("CI 77891", "titanium dioxide"),
    ("Pyrithione Zinc", "zinc pyrithione"), ("Limonene*", "limonene"), ("Phenoxyethanol.", "phenoxyethanol"),
])
def test_exact_names_and_synonyms(raw, expected):
    r = normalize(raw, 1)
    assert (r["normalized"], r["matched"], r["confidence"]) == (expected, True, 1.0)


def test_parabens_are_not_merged():
    # methylparaben is allowed with limits; isopropylparaben is banned in the EU
    assert normalize("Methylparaben", 1)["normalized"] == "methylparaben"
    assert normalize("Isopropylparaben", 1)["normalized"] == "isopropylparaben"


def test_ocr_typos_are_recognised_with_lower_confidence():
    r = normalize("Phenoxyethan0l", 1)
    assert r["normalized"] == "phenoxyethanol" and r["matched"] and r["confidence"] < 1.0
    assert normalize("Ethylhexyl Sterate", 1)["normalized"] == "ethylhexyl stearate"


def test_numbered_names_are_never_swapped():
    assert normalize("Benzophenone-4", 1)["normalized"] == "benzophenone-4"
    assert normalize("Benzophenone-3", 1)["normalized"] == "benzophenone-3"


def test_unknown_text_is_unmatched_with_zero_confidence():
    r = normalize("Xyl0-blend", 1)
    assert (r["matched"], r["confidence"]) == (False, 0.0)


@pytest.mark.parametrize("text", ["Ingredients: Aqua; Glycerin; Parfum", "Aqua\nGlycerin\nParfum", "AQUA, GLYCERIN. PARFUM"])
def test_splitting_handles_label_formats(text):
    assert [i["normalized"] for i in normalize_list(text)[0]] == ["aqua", "glycerin", "parfum"]


def test_may_contain_and_brackets():
    assert split_ingredients("Aqua, Glycerin. May contain: CI 77891, CI 77491") == ["Aqua", "Glycerin", "CI 77891", "CI 77491"]
    assert split_ingredients("Aqua, Parfum (Fragrance, Perfume), Glycerin") == ["Aqua", "Parfum (Fragrance, Perfume)", "Glycerin"]


def test_duplicates_and_review_flag():
    ings, review = normalize_list("Aqua, Water, Glycerin")
    assert [i["normalized"] for i in ings] == ["aqua", "glycerin"] and [i["position"] for i in ings] == [1, 2]
    assert review is False
    assert normalize_list("Aqua, Xyl0-blend")[1] is True
