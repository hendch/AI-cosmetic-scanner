"""Evaluate the toxicology agent against eval/toxicology/gold.json.

Usage (from the repo root):
    python -m scripts.eval_toxicology --mode rules                       # retrieval + rules, no LLM (baseline)
    python -m scripts.eval_toxicology --mode live --prompts v6 v7        # real LLM from .env, about 30-50 calls per prompt
    python -m scripts.eval_toxicology --mode live --prompts v7 --cases sunscreen   # only the cases whose key contains "sunscreen"
    python -m scripts.eval_toxicology --replay v7      # re-score the latest live run of v7, no LLM
    python -m scripts.eval_toxicology --replay eval/toxicology/results_live_v7_2026-10-19_1930.json   # or a given run

Live runs record every model answer ("raw_answers"). --replay feeds them back in the same order, so a code
change (validation, rules) can be re-scored without credits. If the new code asks for a call the recording
does not have (e.g. a retry that did not happen live), that call fails and the ingredient falls back:
"replay_missing" counts them.

Metrics per run (gold fields are explained in gold.json "_meta"):
- concern accuracy     concern_level == expected (or in the accepted list)
- finding recall       ingredients with sccs_required that got at least one correct SCCS finding
- finding precision    SCCS findings that cite an accepted opinion, give only accepted limits and no label_must_not text
- coverage accuracy    "covers": false -> the interpretation says the opinion does not cover this product;
                       true -> it does not say so. Read from the wording (NOT_COVERED), so check the errors by hand.
- ungrounded numbers   quantities in risk_interpretation not in any quote of the finding (should stay 0)
- wording violations   verdict words in risk_interpretation or SCCS labels (should stay 0)
- citation validity    sources registered in corpus/sources.csv
- LLM calls, retries, fallbacks (partial = SCCS findings kept with the rule text), rejected findings,
  label rewordings, seconds
Results go to eval/toxicology/results_<mode>_<prompt>_<time>.json (never overwritten) and a table is printed.
"""

import argparse
import csv
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.common.llm import model_name
from app.common_schemas import ProductInput
from app.toxicology import agent as tox_agent

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval" / "toxicology"
FOLDERS = {"regulatory": ROOT / "eval" / "regulatory" / "products", "samples": ROOT / "samples" / "input",
           "toxicology": EVAL / "products"}
NOT_COVERED = re.compile(
    r"\b(?:does|do|did)\s+not\s+(?:cover|apply|include)|\bnot\s+(?:been\s+)?(?:assessed|covered|evaluated|included)\b|"
    r"\bonly\s+(?:covers?|assessed|applies)\b|\bcovers?\b[^.]{0,80}\bonly\b(?!\s+if)|\bbut not\b|"
    r"\bno\s+(?:sccs\s+)?(?:data|assessment|conclusion)\s+for\s+(?:this|its)\b", re.I)


def _known_sources() -> set[str]:
    with (ROOT / "corpus" / "sources.csv").open(encoding="utf-8") as f:
        return {r["source_id"] for r in csv.DictReader(f)}


def _load_product(key: str) -> ProductInput:
    folder, name = key.split("/")
    return ProductInput.model_validate_json((FOLDERS[folder] / f"{name}.json").read_text(encoding="utf-8"))


def _ingredient_of(messages: list[dict]) -> str | None:
    m = re.search(r"^INGREDIENT: (.+)$", messages[1]["content"], re.M)
    return m.group(1).strip() if m else None


def _recording_chat(key: str, raw: list[dict]):
    from app.common.llm import chat_function

    chat = chat_function()

    def recorded(messages, temperature, max_tokens):
        text = chat(messages, temperature, max_tokens)
        raw.append({"case": key, "ingredient": _ingredient_of(messages), "text": text})
        return text

    return recorded


def _replay_chat(key: str, recorded: dict[tuple, list[str]]):
    def replay(messages, temperature, max_tokens):
        answers = recorded.get((key, _ingredient_of(messages)))
        if not answers:
            raise RuntimeError("replay: no recorded answer for this call")
        return answers.pop(0)

    return replay


def _q(text: str) -> set:
    return tox_agent._quantities(tox_agent._squash(text))


def _limits(values: list[str]) -> set:
    return set().union(*(_q(v) for v in values)) if values else set()


def _score_finding(f, exp: dict, key: str, n: dict, errors: list[str], known: set[str]) -> None:
    ing = f.ingredient
    levels = exp["concern"] if isinstance(exp["concern"], list) else [exp["concern"]]
    n["concern"] += 1
    if f.concern_level in levels:
        n["concern_ok"] += 1
    else:
        errors.append(f"{key} {ing}: concern {f.concern_level} != {'/'.join(levels)}")

    sccs = [h for h in f.hazards if h.classification.startswith("SCCS: ")]
    accepted = set(exp.get("sccs", []))
    good = 0
    for h in sccs:
        label = h.classification.removeprefix("SCCS: ")
        n["findings"] += 1
        problem = None
        if h.source_id not in accepted:
            problem = f"cites {h.source_id}, expected {sorted(accepted) or 'no SCCS finding'}"
        elif "limits" in exp and _q(label) - _limits(exp["limits"]):
            problem = f"limit {sorted(f'{v:g} {u}' for v, u in _q(label))} not in {exp['limits']} for this product"
        elif any(bad.lower() in label.lower() for bad in exp.get("label_must_not", [])):
            problem = f"label contains one of {exp['label_must_not']}"
        if problem:
            errors.append(f"{key} {ing}: finding {label!r} {problem}")
        else:
            good += 1
    n["findings_ok"] += good
    if accepted and exp.get("sccs_required", True):
        n["recall"] += 1
        if good:
            n["recall_ok"] += 1
        elif not sccs:
            errors.append(f"{key} {ing}: no SCCS finding (expected one from {sorted(accepted)})")

    if exp.get("covers") is not None:
        n["coverage"] += 1
        says_not_covered = bool(NOT_COVERED.search(f.risk_interpretation))
        if says_not_covered != (not exp["covers"]):
            errors.append(f"{key} {ing}: coverage expected {'covered' if exp['covers'] else 'NOT covered'}: "
                          f"{f.risk_interpretation!r}")
        else:
            n["coverage_ok"] += 1

    quoted = set().union(*(_q(h.quote) for h in sccs)) if sccs else set()
    extra = _q(f.risk_interpretation) - quoted
    if extra:
        n["ungrounded"] += 1
        errors.append(f"{key} {ing}: numbers {sorted(f'{v:g} {u}' for v, u in extra)} not in any quote: "
                      f"{f.risk_interpretation!r}")
    texts = [f.risk_interpretation] + [h.classification for h in sccs]
    if any(tox_agent.VERDICT_WORDS.search(t) for t in texts):
        n["wording"] += 1
        errors.append(f"{key} {ing}: verdict wording in {texts}")
    for s in f.sources:
        n["cites"] += 1
        n["cites_ok"] += s in known


def evaluate(mode: str, prompt_version: str | None, cases: str | None = None, replay: dict | None = None) -> dict:
    gold = json.loads((EVAL / "gold.json").read_text(encoding="utf-8"))["cases"]
    known = _known_sources()
    prompt = tox_agent.load_prompt(prompt_version) if mode != "rules" else None
    recorded = defaultdict(list)
    for a in (replay or {}).get("raw_answers", []):
        recorded[(a["case"], a["ingredient"])].append(a["text"])
    n = defaultdict(int)
    run = dict(llm_calls=0, retries=0, fallbacks=0, partial_fallbacks=0, rejected_findings=0, label_rewordings=0,
               replay_missing=0)
    errors, raw, t0 = [], [], time.time()
    for key, expected in gold.items():
        if cases and cases not in key:
            continue
        payload = _load_product(key)
        if mode == "rules":
            resp = tox_agent.analyze(payload, mode="rules")
        else:
            chat = _replay_chat(key, recorded) if mode == "replay" else _recording_chat(key, raw)
            resp = tox_agent.analyze(payload, chat=chat, prompt=prompt)
        st = resp.run
        run["llm_calls"] += st.llm_calls
        run["retries"] += st.retries
        run["fallbacks"] += st.fallbacks
        run["rejected_findings"] += len(st.rejected_findings)
        run["label_rewordings"] += sum("label reworded" in i for i in st.llm_issues)
        run["partial_fallbacks"] += sum("validated SCCS findings kept" in w for w in resp.warnings)
        run["replay_missing"] += sum("(RuntimeError)" in w for w in resp.warnings)
        by_name = {f.ingredient: f for f in resp.findings}
        for ing, exp in expected.items():
            _score_finding(by_name[ing], exp, key, n, errors, known)

    pct = lambda a, b: round(100 * a / b, 1) if b else None
    return {
        "mode": mode, "prompt_version": prompt.version if prompt else "rules",
        "model": model_name() if mode == "live" else (replay or {}).get("model"),
        "date": datetime.now().isoformat(timespec="minutes"), "cases_filter": cases,
        "concern_accuracy": pct(n["concern_ok"], n["concern"]),
        "finding_recall": pct(n["recall_ok"], n["recall"]),
        "finding_precision": pct(n["findings_ok"], n["findings"]),
        "coverage_accuracy": pct(n["coverage_ok"], n["coverage"]),
        "ungrounded_numbers": n["ungrounded"], "wording_violations": n["wording"],
        "citation_validity": pct(n["cites_ok"], n["cites"]),
        "ingredients": n["concern"], "sccs_findings": n["findings"],
        **run, "seconds": round(time.time() - t0, 1), "errors": errors,
        "raw_answers": raw if mode == "live" else (replay or {}).get("raw_answers", []),
    }


def _replay_file(arg: str) -> Path:
    """'v7' -> the newest eval/toxicology/results_live_v7_*.json; otherwise a path."""
    if re.fullmatch(r"v\d+", arg):
        runs = sorted(EVAL.glob(f"results_live_{arg}_*.json"))
        if not runs:
            raise SystemExit(f"No live run of {arg} to replay yet. Record one first:\n"
                             f"  python -m scripts.eval_toxicology --mode live --prompts {arg}")
        return runs[-1]
    path = Path(arg)
    if not path.is_file():
        raise SystemExit(f"{arg} not found. Live runs: "
                         f"{[p.name for p in sorted(EVAL.glob('results_live_*.json'))] or 'none yet'}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rules", "live"], default="rules")
    ap.add_argument("--prompts", nargs="*", default=[tox_agent.DEFAULT_PROMPT])
    ap.add_argument("--cases", help="only gold cases whose key contains this text")
    ap.add_argument("--replay", help="a prompt version (latest live run of it, e.g. v7) or the path of a live "
                                     "results JSON: re-score its recorded answers")
    args = ap.parse_args()

    if args.replay:
        recorded = json.loads(_replay_file(args.replay).read_text(encoding="utf-8"))
        results = [evaluate("replay", recorded["prompt_version"], args.cases or recorded.get("cases_filter"), recorded)]
    elif args.mode == "rules":
        results = [evaluate("rules", None, args.cases)]
    else:
        results = [evaluate("live", v, args.cases) for v in args.prompts]

    cols = ["prompt_version", "concern_accuracy", "finding_recall", "finding_precision", "coverage_accuracy",
            "ungrounded_numbers", "wording_violations", "citation_validity", "llm_calls", "retries", "fallbacks",
            "partial_fallbacks", "rejected_findings", "label_rewordings", "seconds"]
    print("| mode | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols))
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    for r in results:
        print(f"| {r['mode']} | " + " | ".join(str(r[c]) for c in cols) + " |")
        out = EVAL / f"results_{r['mode']}_{r['prompt_version']}_{stamp}.json"
        out.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  -> {out.relative_to(ROOT)}")
    for r in results:
        if r["replay_missing"]:
            print(f"\n{r['replay_missing']} call(s) had no recorded answer (the code now asks for more calls than the live run).")
        if r["errors"]:
            print(f"\nErrors ({r['mode']} {r['prompt_version']}):\n  " + "\n  ".join(r["errors"]))


if __name__ == "__main__":
    main()
