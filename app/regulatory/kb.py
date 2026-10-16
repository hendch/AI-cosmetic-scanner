"""Loads the regulatory corpus (corpus/regulatory/) into memory.

Used by the mock and as the stand-in for retrieval until Haroun's endpoint exists.
The real agent asks retrieval for passages; this module is only the local copy.
"""

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus" / "regulatory"
ANNEX_FILES = ["ii", "iii", "iv", "v", "vi"]
SCOPE_SOURCE_ID = "regulatory_scope"


@dataclass(frozen=True)
class AnnexRow:
    source_id: str
    annex: str
    entry: str
    status: str  # "prohibited" | "restricted"
    ingredients: tuple[str, ...]
    inci_names: str
    chemical_name: str
    cas: str
    product_type_body_parts: str
    max_concentration: str
    other_conditions: str
    warnings: str
    consolidated_version: str
    source_url: str

    @property
    def ref(self) -> str:
        return f"{self.annex}/{self.entry}"

    def as_text(self) -> str:
        """Readable passage, the same text a structure-aware chunk would hold."""
        parts = [
            f"Regulation (EC) No 1223/2009, Annex {self.annex}, entry {self.entry} "
            f"(consolidated version {self.consolidated_version}).",
            f"Substance: {self.chemical_name}. INCI: {self.inci_names}. CAS: {self.cas or 'n/a'}.",
        ]
        if self.annex == "II":
            parts.append("Listed in Annex II: prohibited in cosmetic products.")
        if self.product_type_body_parts:
            parts.append(f"Product type, body parts: {self.product_type_body_parts}")
        if self.max_concentration:
            parts.append(f"Maximum concentration in ready for use preparation: {self.max_concentration}")
        if self.other_conditions:
            parts.append(f"Other: {self.other_conditions}")
        if self.warnings:
            parts.append(f"Wording of conditions of use and warnings: {self.warnings}")
        return "\n".join(parts)


@dataclass
class RegulatoryKB:
    rows: list[AnnexRow]
    scope: dict[str, str]  # alias or name -> canonical ingredient
    by_ingredient: dict[str, list[AnnexRow]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for row in self.rows:
            for ing in row.ingredients:
                self.by_ingredient.setdefault(ing, []).append(row)

    def canonical(self, name: str) -> str | None:
        """Canonical ingredient name if it is in the corpus scope, else None."""
        return self.scope.get(name.strip().lower())

    def entries_for(self, canonical: str) -> list[AnnexRow]:
        return self.by_ingredient.get(canonical, [])


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def load_kb(corpus_dir: Path = CORPUS_DIR) -> RegulatoryKB:
    rows: list[AnnexRow] = []
    for annex in ANNEX_FILES:
        source_id = f"eu_1223_2009_annex_{annex}"
        for r in _read_csv(corpus_dir / f"{source_id}.csv"):
            rows.append(
                AnnexRow(
                    source_id=source_id,
                    annex=r["annex"],
                    entry=r["entry"],
                    status=r["status"],
                    ingredients=tuple(i.strip() for i in r["ingredients"].split(";") if i.strip()),
                    inci_names=r["inci_names"],
                    chemical_name=r["chemical_name"],
                    cas=r["cas"],
                    product_type_body_parts=r["product_type_body_parts"],
                    max_concentration=r["max_concentration"],
                    other_conditions=r["other_conditions"],
                    warnings=r["warnings"],
                    consolidated_version=r["consolidated_version"],
                    source_url=r["source_url"],
                )
            )

    scope: dict[str, str] = {}
    for r in _read_csv(corpus_dir / "regulatory_scope.csv"):
        name = r["ingredient"].strip().lower()
        scope[name] = name
        for alias in r["aliases"].split(";"):
            if alias.strip():
                scope[alias.strip().lower()] = name
    return RegulatoryKB(rows=rows, scope=scope)
