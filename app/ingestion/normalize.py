"""Ingredient text -> normalized INCI names.

`matched` means "recognised as a real INCI ingredient" (EU CosIng names via the Open Beauty Facts
taxonomy, built by scripts/build_inci_dictionary.py). Whether the corpus covers that ingredient is
for each agent to decide. `confidence` is how sure we are of THIS name: 1.0 for an exact name or
synonym, the similarity score for an OCR-typo match, 0.0 when nothing matched.
"""

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

DICTIONARY = Path(__file__).resolve().parent / "data" / "inci_dictionary.json.gz"

FUZZY_CUTOFF = 90  # similarity (0-100) needed to accept a typo match
REVIEW_BELOW = 0.95  # confidence under this marks the product for review
# Label noise in front of the list: "Ingredients:", "INGRÉDIENTS :", "INCI:", "Composition:"
PREFIX = re.compile(r"^\s*(ingredients?|ingr[ée]dients?|inci|composition|zutaten|ingredientes)\s*[:\-]\s*", re.IGNORECASE)
# "May contain / Peut contenir / [+/-]": colorants that may be present; they are still listed ingredients.
MAY_CONTAIN = re.compile(r"\b(may contain|peut contenir|kann enthalten|\+/-)\s*:?", re.IGNORECASE)
# Common OCR confusions inside words: digit read instead of a letter.
OCR_DIGITS = str.maketrans({"0": "o", "1": "l", "5": "s"})


@lru_cache(maxsize=1)
def dictionary() -> dict[str, str]:
    with gzip.open(DICTIONARY, "rt", encoding="utf-8") as f:
        return json.load(f)["names"]


@lru_cache(maxsize=1)
def _keys() -> list[str]:
    return list(dictionary())


def split_ingredients(text: str) -> list[str]:
    """Split an ingredient list on commas, semicolons, bullets, '. ' and new lines, but not inside brackets."""
    text = MAY_CONTAIN.sub(",", PREFIX.sub("", text or ""))
    parts, depth, current = [], 0, []
    for n, ch in enumerate(text):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(depth - 1, 0)
        # ". " also separates (INCI names never contain it; decimals like 0.5 have no space)
        period = ch == "." and text[n + 1:n + 2].isspace()
        if depth == 0 and (ch in ",;•·\n\r" or period):
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .*:-\t")
        p = re.sub(r"^\d+(\.\d+)?\s*%\s*", "", p)  # "2% Niacinamide" (rare, but some brands print it)
        if p and len(p) > 1:
            out.append(p)
    return out


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.lower().replace("*", "")).strip(" .:")


def _candidates(raw: str) -> list[str]:
    """Ways a label may write one ingredient: as is, without the bracket, the bracket alone, each '/' part."""
    c = _clean(raw)
    out = [c]
    no_bracket = re.sub(r"\s*\([^)]*\)", "", c).strip()
    out.append(no_bracket)
    out += [b.strip() for b in re.findall(r"\(([^)]*)\)", c)]
    for variant in (c, no_bracket):
        if "/" in variant:
            out += [part.strip() for part in variant.split("/")]
    return [x for x in dict.fromkeys(out) if x]


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def normalize(raw: str, position: int) -> dict:
    names = dictionary()
    candidates = _candidates(raw)
    for c in candidates:  # exact name or synonym
        if c in names:
            return {"position": position, "raw": raw, "normalized": names[c], "matched": True, "confidence": 1.0}

    best = None
    for c in candidates[:2]:  # typo tolerance on the full name only, not on fragments
        fixed = re.sub(r"(?<=[a-z])[015](?=[a-z])|(?<=[a-z])[015]$", lambda m: m.group(0).translate(OCR_DIGITS), c)
        if len(fixed) < 5:
            continue
        if fixed in names:
            return {"position": position, "raw": raw, "normalized": names[fixed], "matched": True, "confidence": 0.95}
        hit = process.extractOne(fixed, _keys(), scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF)
        # Never swap numbered names: benzophenone-3 must not become benzophenone-4.
        if hit and _digits(hit[0]) == _digits(fixed) and (best is None or hit[1] > best[1]):
            best = hit
    if best:
        return {"position": position, "raw": raw, "normalized": names[best[0]], "matched": True,
                "confidence": round(best[1] / 100, 2)}
    return {"position": position, "raw": raw, "normalized": _clean(raw), "matched": False, "confidence": 0.0}


def normalize_list(text: str) -> tuple[list[dict], bool]:
    """(ingredients, needs_review). Duplicate names (e.g. 'Aqua' and 'Water') keep their first position."""
    return normalize_items(split_ingredients(text))


def normalize_items(raw_names: list[str]) -> tuple[list[dict], bool]:
    """Same as normalize_list for names already split one per item (label OCR returns them that way)."""
    seen, out = set(), []
    for raw in (r.strip() for r in raw_names):
        if not raw:
            continue
        ing = normalize(raw, len(out) + 1)
        if ing["matched"] and ing["normalized"] in seen:
            continue
        seen.add(ing["normalized"])
        out.append(ing)
    needs_review = any(not i["matched"] or i["confidence"] < REVIEW_BELOW for i in out)
    return out, needs_review
