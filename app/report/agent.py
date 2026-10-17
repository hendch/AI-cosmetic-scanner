"""Validator agent: checks every claim in the draft report against its cited excerpts.

The prompt comes from prompts/validator/<version>.yaml. The cited excerpts travel inside
the draft (draft.sources), so one model call is enough; no tool loop.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.common import llm
from app.report.schemas import Draft, ValidateResponse, ValidatorOutput

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "validator"
MAX_ATTEMPTS = 2  # one retry with the schema error; credits are shared


class ValidatorError(RuntimeError):
    pass


@lru_cache
def load_prompt(version: str) -> dict:
    path = PROMPTS_DIR / f"{version}.yaml"
    if not path.exists():
        raise ValidatorError(f"Unknown validator prompt version {version}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _extract_json(text: str) -> str:
    """Small models often wrap JSON in ```json fences or add a sentence around it."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def validate_draft(draft: Draft, version: str = "v4") -> ValidateResponse:
    prompt = load_prompt(version)
    payload = draft.model_dump(mode="json", include={"ingredients", "cruelty_free", "sources"})
    messages = [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": prompt["user"].replace("{draft}", json.dumps(payload, ensure_ascii=False))},
    ]
    temperature = prompt["model_params"]["temperature"]

    answer, problem = "", ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        answer = llm.chat(messages, temperature=temperature)
        try:
            result = ValidatorOutput.model_validate_json(_extract_json(answer))
            return ValidateResponse(prompt_version=version, model=llm.model_name(), attempts=attempt, result=result)
        except ValidationError as exc:
            problem = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])
            messages += [
                {"role": "assistant", "content": answer},
                {"role": "user", "content": f"Your answer did not match the required JSON schema ({problem}). Return only the corrected JSON object."},
            ]
    raise ValidatorError(
        f"The model did not return valid JSON after {MAX_ATTEMPTS} attempts ({problem}). Last answer starts: {answer[:300]!r}"
    )
