"""Replay recorded LLM answers through the regulatory agent (no network, no cost).

Usage: python -m scripts.replay_regulatory [eval/regulatory/live_answers_<date>_<version>.json]

Shows exactly what the agent returns for real model answers: which safety rules fired,
whether a retry was needed, and the final findings.
"""

import json
import sys
from pathlib import Path

from app.common_schemas import ProductInput
from app.regulatory.agent import analyze
from app.regulatory.agent import load_prompt

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "eval" / "regulatory" / "live_answers_2026-10-16_v3.json"


def main(path: Path = DEFAULT) -> dict:
    answers = json.loads(path.read_text(encoding="utf-8"))
    meta = answers.pop("_meta", {})
    results = {}
    for sample in sorted({k.split("|")[0] for k in answers}):
        payload = ProductInput.model_validate_json((ROOT / "samples" / "input" / f"{sample}.json").read_text(encoding="utf-8"))

        def chat(messages, temperature, max_tokens, sample=sample):
            ingredient = messages[1]["content"].split("INGREDIENT: ")[1].split(" (")[0]
            return answers[f"{sample}|{ingredient}"]["text"]

        response = analyze(payload, chat=chat, prompt=load_prompt(meta.get("prompt_version")))
        results[sample] = response.model_dump(mode="json")
        print(f"== {sample}  (calls={response.run.llm_calls}, retries={response.run.retries}, fallbacks={response.run.fallbacks})")
        for f in response.findings:
            conds = ", ".join(f"{c.type}:{c.result}" for c in f.conditions)
            print(f"  {f.ingredient:22} {f.regulatory_status:21} {f.compliance_check:14} [{conds}]")
            if f.conditions:
                print(f"  {'':22} -> {f.explanation}")
        for o in response.run.overrides:
            print(f"  override: {o}")
    return results


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
