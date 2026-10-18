"""Build app/ingestion/data/inci_dictionary.json.gz, the ingredient-name lookup used by normalization.

Source: the Open Beauty Facts beauty ingredients taxonomy (ODbL), derived from the EU CosIng database:
https://github.com/openfoodfacts/openfoodfacts-server/blob/main/taxonomies/beauty/ingredients-cosing-obf.txt
Each entry gives the INCI name and synonyms in several languages (aqua = water = eau = wasser ...).
The corpus aliases (corpus/regulatory/regulatory_scope.csv) are added on top so names always match the agents.

Usage: python -m scripts.build_inci_dictionary [path-or-url]
"""

import csv
import gzip
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/"
       "taxonomies/beauty/ingredients-cosing-obf.txt")
OUT = ROOT / "app" / "ingestion" / "data" / "inci_dictionary.json.gz"
SCOPE_CSV = ROOT / "corpus" / "regulatory" / "regulatory_scope.csv"

LANGUAGE_LINE = re.compile(r"^([a-z]{2}):\s*(.+)$")  # "en: AQUA, water", "fr: eau", "xx: aqua"
DESCRIPTION_LINE = re.compile(r"^inci_description:en:\s*(.+)$")


# EU labels use the INCI name PARFUM; "fragrance" / "perfume" are how it is often printed next to it.
OVERRIDES = {"fragrance": "parfum", "perfume": "parfum", "parfum/fragrance": "parfum"}
# Common INCI names (EU CosIng) missing from the Open Beauty Facts file, found on real labels.
# Add a name here only after checking it in CosIng: https://ec.europa.eu/growth/tools-databases/cosing/
SUPPLEMENT = [
    "hydrogenated castor oil",
    "peg-40 hydrogenated castor oil",
]


def key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def without_brackets(name: str) -> str:
    """'helianthus annuus (sunflower) seed oil' -> 'helianthus annuus seed oil' (how labels often print it)."""
    return key(re.sub(r"\s*\([^)]*\)", "", name))


def parse(text: str) -> dict[str, str]:
    """synonym -> canonical INCI name (lowercase). Synonyms shared by two entries are dropped."""
    canonical: dict[str, str] = {}
    synonyms: dict[str, set[str]] = {}
    for block in re.split(r"\n\s*\n", text):
        lines = [l.strip() for l in block.splitlines() if l.strip() and not l.startswith("#")]
        en = next((LANGUAGE_LINE.match(l) for l in lines if l.startswith("en:")), None)
        if not en:
            continue
        names = [key(n) for n in en.group(2).split(",") if n.strip()]
        inci = names[0]
        canonical[inci] = inci
        for line in lines:
            m = LANGUAGE_LINE.match(line)
            if m:
                for n in m.group(2).split(","):
                    synonyms.setdefault(key(n), set()).add(inci)
            d = DESCRIPTION_LINE.match(line)
            if d and len(d.group(1).split()) <= 3:  # short chemical names ("Glycerol"), not sentences
                synonyms.setdefault(key(d.group(1)), set()).add(inci)
    for inci in list(canonical):
        short = without_brackets(inci)
        if short and short != inci:
            synonyms.setdefault(short, set()).add(inci)
    out = dict(canonical)
    for name, targets in synonyms.items():
        if name not in out and len(targets) == 1 and name:
            out[name] = next(iter(targets))
    return out


def corpus_aliases() -> dict[str, str]:
    out = {}
    with SCOPE_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            name = key(r["ingredient"])
            out[name] = name
            for alias in r["aliases"].split(";"):
                if alias.strip():
                    out[key(alias)] = name
    return out


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else URL
    text = requests.get(src, timeout=60).text if src.startswith("http") else Path(src).read_text(encoding="utf-8")
    names = parse(text)
    names.update({n: n for n in SUPPLEMENT if n not in names})
    names.update(OVERRIDES)
    names.update(corpus_aliases())  # the agents' names win
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump({"source": URL, "licence": "ODbL (Open Beauty Facts), derived from EU CosIng",
                   "names": dict(sorted(names.items()))}, f, ensure_ascii=False, separators=(",", ":"))
    inci = len(set(names.values()))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(names)} names for {inci} INCI ingredients ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
