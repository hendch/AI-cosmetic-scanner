"""How many ingredient names on real products the normalizer recognises (no model calls).

The products are a saved snapshot of the most-scanned German products on Open Beauty Facts (ODbL),
in eval/normalize/products.json, so the numbers do not move when OBF changes.
Lists that are not ingredient lists (food, marketing text, a single unsplittable line) are skipped.

Usage: python -m scripts.eval_normalize            score the snapshot, write eval/normalize/results.md
       python -m scripts.eval_normalize --fetch    refresh the snapshot first (one OBF request)
"""

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from app.ingestion.normalize import normalize_list

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval" / "normalize"
SNAPSHOT = EVAL_DIR / "products.json"
SEARCH = ("https://world.openbeautyfacts.org/api/v2/search?countries_tags=en:germany"
          "&fields=code,product_name,brands,ingredients_text&page_size=60&sort_by=unique_scans_n")


def fetch() -> None:
    products = requests.get(SEARCH, timeout=60, headers={"User-Agent": "cosmetic-scanner-eval"}).json()["products"]
    keep = [{k: p.get(k) for k in ("code", "brands", "product_name", "ingredients_text")}
            for p in products if len(p.get("ingredients_text") or "") >= 40]
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps({"source": SEARCH, "licence": "ODbL (Open Beauty Facts)", "fetched": date.today().isoformat(),
                                    "products": keep}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved {len(keep)} products to {SNAPSHOT.relative_to(EVAL_DIR.parents[1])}")


def looks_like_inci(items: list[dict]) -> bool:
    """Skip food lists and marketing text: an INCI list has several items and few long ones."""
    long = sum(len(i["raw"]) > 60 for i in items)
    return len(items) >= 5 and long <= 1


def run() -> None:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    total, exact, fuzzy, skipped = 0, 0, 0, []
    unmatched: Counter[str] = Counter()
    for p in data["products"]:
        items, _ = normalize_list(p["ingredients_text"])
        if not looks_like_inci(items):
            skipped.append(p["code"])
            continue
        for i in items:
            total += 1
            if i["matched"] and i["confidence"] >= 1.0:
                exact += 1
            elif i["matched"]:
                fuzzy += 1
            else:
                unmatched[i["raw"].lower()] += 1
    scored = len(data["products"]) - len(skipped)
    pct = lambda n: f"{100 * n / total:.1f} %"
    lines = [
        "# Ingredient-name recognition on real products",
        "",
        f"Snapshot: {len(data['products'])} most-scanned German products on Open Beauty Facts, fetched {data['fetched']}.",
        f"Scored: {scored} products with an ingredient list ({len(skipped)} skipped: food, marketing text or one unsplit line).",
        "",
        "| Ingredient names | Count | Share |",
        "|---|---|---|",
        f"| Recognised exactly (dictionary or alias) | {exact} | {pct(exact)} |",
        f"| Recognised after typo correction | {fuzzy} | {pct(fuzzy)} |",
        f"| Not recognised | {total - exact - fuzzy} | {pct(total - exact - fuzzy)} |",
        f"| Total | {total} | |",
        "",
        "Most frequent names not recognised:",
        "",
    ]
    lines += [f"- {name} ({n})" for name, n in unmatched.most_common(25)]
    (EVAL_DIR / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    run()
