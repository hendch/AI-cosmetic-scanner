"""Run the five end-to-end scenarios through the n8n webhook and record the answers.

Each scenario is one request (the OCR fallback is two: the barcode, then the label photo), exactly as
the app sends it. Answers go to eval/scenarios/<run>/, with a summary table in summary.md.

Model calls (shared credits): about one per restricted ingredient (regulatory agent), one per scan for
the validator, one for the label photo. About 20 for the whole run; the script prints nothing secret.

Usage: python -m scripts.run_scenarios [webhook-url] [--only 3_unknown_ingredient,...]
       default http://localhost:5678/webhook/cosmetic-scanner-live (docker compose)
       online: https://<n8n-service>.onrender.com/webhook/cosmetic-scanner-live
The app key is read from EXPO_PUBLIC_WEBHOOK_KEY in .env.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
ARGS = sys.argv[1:]
ONLY = ARGS.pop(ARGS.index("--only") + 1).split(",") if "--only" in ARGS else None
ARGS = [a for a in ARGS if a != "--only"]
URL = ARGS[0] if ARGS else "http://localhost:5678/webhook/cosmetic-scanner-live"
CERAVE_LABEL = "https://images.openbeautyfacts.org/images/products/333/787/559/7197/ingredients_en.3.full.jpg"

# (id, what it shows, requests)
SCENARIOS = [
    ("1_barcode_found", "Barcode in Open Beauty Facts: ingredient list from the database, full report.",
     [{"barcode": "4066447870213"}]),
    ("2_ocr_fallback", "Barcode not in Open Beauty Facts: the app is asked for a label photo; the photo is read by OCR.",
     [{"barcode": "3600523351350"}, {"label_image_ref": CERAVE_LABEL}]),
    ("3_unknown_ingredient", "Ingredient names the dictionary does not know: shown as not recognised, not assessed.",
     [{"barcode": "3574660085563"}]),
    ("4_missing_concentration", "Restricted ingredients whose limit depends on a concentration the label does not give.",
     [{"barcode": "4066447982596"}]),
    ("5_no_cruelty_free_evidence", "No brand claim or certification found: animal testing reported as not verified.",
     [{"barcode": "4305615657196"}]),
]


def post(body: dict) -> tuple[dict, float]:
    full = {"barcode": None, "barcode_image_ref": None, "label_image_ref": None, **body}
    started = time.time()
    r = requests.post(URL, json=full, timeout=300,
                      headers={"X-API-Key": os.environ.get("EXPO_PUBLIC_WEBHOOK_KEY", "")})
    r.raise_for_status()
    return r.json(), round(time.time() - started, 1)


def summary(answer: dict) -> dict:
    rep = answer.get("report")
    if not rep:
        return {"status": answer.get("status"),
                "message": (answer.get("next_action") or {}).get("message") or (answer.get("error") or {}).get("message")}
    ings = rep["ingredients"]
    checks = rep["validation"]["checks"]
    ai = next((c for c in checks if c["name"] == "ai_validator"), None)
    return {
        "status": answer["status"],
        "product": f"{rep['product']['brand']} {rep['product']['name']}".strip(),
        "input_source": rep["input_source"],
        "ingredients": len(ings),
        "not_recognised": [i["raw"] for i in ings if not i["matched"]],
        "restricted": [f"{i['ingredient_id']} ({', '.join(i['regulatory']['entries'])})" for i in ings
                       if i["regulatory"]["status"] == "restricted"],
        "prohibited": [i["ingredient_id"] for i in ings if i["regulatory"]["status"] == "prohibited"],
        "concentration_unknown": rep["overview"]["concentration_unknown"],
        "cruelty_free": rep["cruelty_free"]["status"],
        "evidence_coverage": f"{rep['evidence_coverage']['covered']}/{rep['evidence_coverage']['total']}",
        "rule_checks_failed": [c["name"] for c in checks if not c["passed"] and c["name"] != "ai_validator"],
        "ai_validator": None if ai is None else ("passed" if ai["passed"] else f"{len(ai['issues'])} issues"),
        "validator_prompt": (answer.get("validator") or {}).get("prompt_version"),
    }


def main() -> None:
    out_dir = ROOT / "eval" / "scenarios" / datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for sid, what, requests_ in SCENARIOS:
        if ONLY and sid not in ONLY:
            continue
        for n, body in enumerate(requests_, 1):
            answer, seconds = post(body)
            name = sid if len(requests_) == 1 else f"{sid}_step{n}"
            (out_dir / f"{name}.json").write_text(json.dumps({"request": body, "seconds": seconds, "answer": answer},
                                                             indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            s = summary(answer)
            rows.append((name, what if n == 1 else "(label photo)", seconds, s))
            print(f"{name}: {s['status']} in {seconds} s")
    lines = [f"# End-to-end scenarios {out_dir.name}", "", f"Webhook: `{URL}`", "",
             "| Scenario | What it shows | Seconds | Result |", "|---|---|---|---|"]
    for name, what, seconds, s in rows:
        result = "; ".join(f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in s.items()
                           if v not in (None, [], ""))
        lines.append(f"| {name} | {what} | {seconds} | {result} |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_dir.relative_to(ROOT)}/summary.md")


if __name__ == "__main__":
    main()
