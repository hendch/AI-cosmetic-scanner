"""Evaluate the regulatory agent against eval/regulatory/gold.json.

Usage (from the repo root):
    python -m scripts.eval_regulatory --mode mock                    # rules only, no LLM (baseline)
    python -m scripts.eval_regulatory --mode live --prompts v1 v2 v3 v4 # real LLM from .env (about 25 calls per prompt)

Metrics per run:
- status accuracy        regulatory_status == expected
- compliance accuracy    compliance_check == expected
- condition accuracy     result of each scored condition (gold "conditions") == expected
- citation validity      every cited source_id exists in corpus/sources.csv and matches the entries found
- wording violations     explanations containing safe/unsafe/illegal/dangerous/toxic
- LLM calls, retries, fallbacks, safety overrides, status disagreements, seconds
In live mode the raw model answers are kept in "raw_answers" (to quote real failures in known_failures).
Results are written to eval/regulatory/results_<mode>_<prompt>.json and printed as a table.
"""

import argparse
import csv
import json
import re
import time
from pathlib import Path

from app.common_schemas import ProductInput
from app.regulatory.agent import load_prompt

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval" / "regulatory"
FORBIDDEN = re.compile(r"\b(safe|safely|unsafe|illegal|unlawful|dangerous|toxic|harmful)\b", re.I)


def _known_sources() -> set[str]:
    with (ROOT / "corpus" / "sources.csv").open(encoding="utf-8") as f:
        return {r["source_id"] for r in csv.DictReader(f)}


def _load_product(key: str) -> ProductInput:
    folder, name = key.split("/")
    path = (EVAL / "products" if folder == "products" else ROOT / "samples" / "input") / f"{name}.json"
    return ProductInput.model_validate_json(path.read_text(encoding="utf-8"))


def _recording_chat(key: str, raw: list[dict]):
    from app.common.llm import chat_function

    chat = chat_function()

    def recorded(messages, temperature, max_tokens):
        m = re.search(r"(?:INGREDIENT|Ingredient): (.+?) \(position", messages[1]["content"])
        text = chat(messages, temperature, max_tokens)
        raw.append({"case": key, "ingredient": m.group(1) if m else None, "text": text})
        return text

    return recorded


def _run(payload: ProductInput, mode: str, prompt_version: str | None, key: str, raw: list[dict]):
    if mode == "mock":
        from app.regulatory.mock import build_mock_response

        return build_mock_response(payload)
    from app.regulatory.agent import analyze

    return analyze(payload, chat=_recording_chat(key, raw), prompt=load_prompt(prompt_version))


def evaluate(mode: str, prompt_version: str | None) -> dict:
    gold = json.loads((EVAL / "gold.json").read_text(encoding="utf-8"))["cases"]
    known = _known_sources()
    n = dict(status=0, status_ok=0, compliance=0, compliance_ok=0, cond=0, cond_ok=0, cites=0, cites_ok=0, wording=0)
    run = dict(llm_calls=0, retries=0, fallbacks=0, overrides=0, status_disagreements=0)
    errors, raw, overrides, t0 = [], [], [], time.time()
    for key, expected in gold.items():
        resp = _run(_load_product(key), mode, prompt_version, key, raw)
        if resp.run:
            for k in run:
                v = getattr(resp.run, k)
                run[k] += len(v) if isinstance(v, list) else v
            overrides += [f"{key}: {o}" for o in resp.run.overrides]
        by_name = {f.ingredient: f for f in resp.findings}
        for ing, exp in expected.items():
            f = by_name[ing]
            n["status"] += 1
            if f.regulatory_status == exp["status"]:
                n["status_ok"] += 1
            else:
                errors.append(f"{key} {ing}: status {f.regulatory_status} != {exp['status']}")
            n["compliance"] += 1
            if f.compliance_check == exp["compliance"]:
                n["compliance_ok"] += 1
            else:
                errors.append(f"{key} {ing}: compliance {f.compliance_check} != {exp['compliance']}")
            for ec in exp.get("conditions", []):
                n["cond"] += 1
                got = [c.result for c in f.conditions if c.entry == ec["entry"] and c.type == ec["type"]]
                if got and all(r == ec["result"] for r in got):
                    n["cond_ok"] += 1
                else:
                    errors.append(f"{key} {ing}: {ec['entry']} {ec['type']} {got} != {ec['result']}")
            entry_sources = {e.source_id for e in f.entries} | ({"regulatory_scope"} if f.regulatory_status == "no_restriction_found" else set())
            for s in f.sources:
                n["cites"] += 1
                n["cites_ok"] += s in known and s in entry_sources
            if FORBIDDEN.search(f.explanation):
                n["wording"] += 1
                errors.append(f"{key} {ing}: wording '{f.explanation}'")
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    return {
        "mode": mode, "prompt_version": prompt_version if mode != "mock" else "mock",
        "status_accuracy": pct(n["status_ok"], n["status"]),
        "compliance_accuracy": pct(n["compliance_ok"], n["compliance"]),
        "condition_accuracy": pct(n["cond_ok"], n["cond"]),
        "citation_validity": pct(n["cites_ok"], n["cites"]),
        "wording_violations": n["wording"],
        "cases": n["status"], "scored_conditions": n["cond"],
        **run, "seconds": round(time.time() - t0, 1), "errors": errors,
        "override_details": overrides, "raw_answers": raw,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mock", "live"], default="mock")
    ap.add_argument("--prompts", nargs="*", default=["v4"])
    args = ap.parse_args()
    results = [evaluate("mock", None)] if args.mode == "mock" else [evaluate("live", v) for v in args.prompts]
    cols = ["prompt_version", "status_accuracy", "compliance_accuracy", "condition_accuracy", "citation_validity",
            "wording_violations", "llm_calls", "retries", "fallbacks", "overrides", "status_disagreements", "seconds"]
    print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for r in results:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
        (EVAL / f"results_{r['mode']}_{r['prompt_version']}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    for r in results:
        if r["errors"]:
            print(f"\nErrors ({r['prompt_version']}):\n  " + "\n  ".join(r["errors"]))


if __name__ == "__main__":
    main()
