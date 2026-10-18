"""Source registry and evidence text for the report.

Agents cite corpus files (`source_id`, corpus/sources.csv). The report needs the exact text each
claim rests on, so this module turns a citation into an evidence item: an annex row, a CLP table
row, the coverage list entry, an article, or the detail an agent supplied.
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.regulatory.kb import load_kb

ROOT = Path(__file__).resolve().parents[2]
SOURCES_CSV = ROOT / "corpus" / "sources.csv"
CLP_CSV = ROOT / "corpus" / "toxicology" / "clp" / "clp_test_ingredients.csv"
SCOPE_CSV = ROOT / "corpus" / "regulatory" / "regulatory_scope.csv"
ARTICLES_DIR = ROOT / "corpus" / "regulatory"

# Citable sources that are product data, not corpus files.
PRODUCT_DATA = {
    "obf_labels": ("Open Beauty Facts product labels", "Open Beauty Facts", "https://world.openbeautyfacts.org"),
}

PLACEHOLDER_MARKERS = ("MOCK", "replace with retrieved text")


@dataclass(frozen=True)
class SourceInfo:
    source_id: str
    title: str
    publisher: str
    date: str | None
    url: str | None
    ingredients: frozenset[str] | None  # None = covers several / unspecified ingredients


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def registry() -> dict[str, SourceInfo]:
    out = {sid: SourceInfo(sid, t, p, None, u, None) for sid, (t, p, u) in PRODUCT_DATA.items()}
    for r in _read(SOURCES_CSV):
        cell = r["ingredients"].strip().lower()
        names = None if cell in ("", "multiple") else frozenset(i.strip() for i in cell.split(";") if i.strip())
        out[r["source_id"]] = SourceInfo(r["source_id"], r["document_title"], r["source"],
                                         r["publication_date"] or None, r["url"] or None, names)
    return out


@lru_cache(maxsize=1)
def _clp_rows() -> dict[str, dict]:
    return {r["ingredient"].strip().lower(): r for r in _read(CLP_CSV)}


@lru_cache(maxsize=1)
def _scope_rows() -> dict[str, dict]:
    return {r["ingredient"].strip().lower(): r for r in _read(SCOPE_CSV)}


def is_placeholder(text: str | None) -> bool:
    return not text or any(m.lower() in text.lower() for m in PLACEHOLDER_MARKERS)


def annex_text(source_id: str, entry: str) -> str:
    for row in load_kb().rows:
        if row.source_id == source_id and row.entry == entry:
            return row.as_text()
    return ""


def scope_text(ingredient: str) -> str:
    r = _scope_rows().get(ingredient.lower())
    if not r:
        return ""
    annexes = r["annexes_checked"].replace(";", ", ")
    return (f"Coverage list: '{r['ingredient']}' was looked up in Annexes {annexes} of Regulation (EC) "
            f"No 1223/2009 (consolidated version {r['consolidated_version']}); no entry was found for it.")


def clp_text(ingredient: str) -> str:
    r = _clp_rows().get(ingredient.lower())
    if not r:
        return ""
    head = f"{r['echa_substance_name']} (CAS {r['cas']})"
    if r["harmonised"].strip().lower() == "yes":
        return (f"{head}: harmonised classification, CLP Annex VI index {r['annex_vi_index_no']} ({r['atp']}): "
                f"{r['hazard_classes']}. Hazard statements: {r['hazard_statements']}.")
    if r["notified_classification"]:
        return f"{head}: no harmonised classification; notified classification: {r['notified_classification']}."
    return f"{head}: no harmonised classification in Annex VI to CLP."


def article_text(source_id: str, limit: int = 1200) -> str:
    path = ARTICLES_DIR / f"{source_id}.md"
    if not path.exists():
        return ""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("Source:")]
    return " ".join(lines)[:limit]
