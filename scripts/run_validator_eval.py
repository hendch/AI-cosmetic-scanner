"""Run the validator agent on eval/validator/cases.json and record the results.

One model call per case and prompt version (plus at most one retry on bad JSON).
Credits are shared: the script prints the number of calls before it starts.

Usage: python -m scripts.run_validator_eval [v1 v2 v3 ...]
       python -m scripts.run_validator_eval --rescore <results.json>   (no model calls)
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from app.report.agent import ValidatorError, validate_draft
from app.common.llm import model_name
from app.report.schemas import Draft, ValidatorOutput

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval" / "validator"
RESULTS_DIR = EVAL_DIR / "results"


def load_cases() -> dict[str, dict]:
    cases = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))
    return {c["case_id"]: c for c in cases}


def score(version: str, case: dict, result: ValidatorOutput) -> dict:
    flags = [
        {
            "agent": agent,
            "ingredient_id": ingredient_id,
            "flagged": any(
                c.agent == agent and c.ingredient_id == ingredient_id and c.verdict != "supported" for c in result.claims
            ),
        }
        for agent, ingredient_id in case["expected_flags"]
    ]
    return {
        "valid": result.valid,
        "verdict_correct": result.valid == case["expected_valid"],
        "expected_flags_found": f"{sum(f['flagged'] for f in flags)}/{len(flags)}" if version != "v1" else "n/a (no claims in v1)",
        "flags": flags,
        "result": result.model_dump(mode="json"),
    }


def write_results(path: Path, model: str, runs: list[dict]) -> None:
    path.with_suffix(".json").write_text(json.dumps({"model": model, "runs": runs}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    got = {True: "valid", False: "invalid", None: "no JSON"}
    lines = [
        f"# Validator evaluation {path.name}",
        "",
        f"Model: `{model}`, temperature 0.",
        "",
        "| Prompt | Case | Expected | Got | Correct | Problems flagged | Attempts | Seconds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        lines.append(
            f"| {run['prompt_version']} | {run['case_id']} | {got[run['expected_valid']]} | {got[run['valid']]} | "
            f"{'yes' if run['verdict_correct'] else 'no'} | {run['expected_flags_found']} | {run['attempts']} | {run['seconds']} |"
        )
    for version in dict.fromkeys(r["prompt_version"] for r in runs):
        mine = [r for r in runs if r["prompt_version"] == version]
        lines += ["", f"{version}: {sum(r['verdict_correct'] for r in mine)}/{len(mine)} verdicts correct."]
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote eval/validator/results/{path.name}.md and .json")


def run(versions: list[str]) -> None:
    cases = load_cases()
    print(f"{len(cases)} cases x {len(versions)} versions = {len(cases) * len(versions)} model calls")
    runs = []
    for version in versions:
        for case in cases.values():
            started = time.time()
            base = {"prompt_version": version, "case_id": case["case_id"], "expected_valid": case["expected_valid"]}
            try:
                response = validate_draft(Draft.model_validate(case["draft"]), version)
            except ValidatorError as exc:
                # A schema failure is a result too: it counts as a wrong verdict.
                runs.append({**base, "valid": None, "verdict_correct": False, "expected_flags_found": "invalid JSON",
                             "flags": [], "attempts": 2, "seconds": round(time.time() - started, 1), "error": str(exc)})
                print(f"{version} {case['case_id']}: invalid JSON after retries")
                continue
            runs.append({**base, **score(version, case, response.result), "attempts": response.attempts,
                         "seconds": round(time.time() - started, 1)})
            print(f"{version} {case['case_id']}: valid={response.result.valid} (expected {case['expected_valid']})")
    RESULTS_DIR.mkdir(exist_ok=True)
    write_results(RESULTS_DIR / datetime.now().strftime("%Y-%m-%d_%H%M"), model_name(), runs)


def rescore(path: Path) -> None:
    """Re-apply the current scoring and schema rules to saved model answers, without calling the model."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = load_cases()
    for entry in data["runs"]:
        if "result" in entry:
            entry.update(score(entry["prompt_version"], cases[entry["case_id"]], ValidatorOutput.model_validate(entry["result"])))
    write_results(path.with_suffix(""), data["model"], data["runs"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["--rescore"]:
        rescore(Path(sys.argv[2]))
    else:
        run(sys.argv[1:] or ["v1", "v2", "v3", "v4"])
