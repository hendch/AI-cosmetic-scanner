"""Validator agent: checks every claim in the report against the text of its cited evidence.

The prompt comes from prompts/validator/<version>.yaml. The evidence text travels inside
the draft (draft.sources), so one model call is enough; no tool loop.
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.common import llm
from app.report.schemas import (
    Draft,
    Report,
    ValidatedReport,
    ValidateResponse,
    Validation,
    ValidationCheck,
    ValidatorOutput,
)

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


def validate_draft(draft: Draft, version: str = "v5") -> ValidateResponse:
    prompt = load_prompt(version)
    payload = draft.model_dump(mode="json", include={"product", "ingredients", "cruelty_free", "sources"})
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


# ---- report -> validator -> report ----------------------------------------------------

AI_CHECK = "ai_validator"
AI_CHECK_DESCRIPTION = "The validator agent found every claim supported by the text of its cited evidence."
# Advisory by default: on real reports the 7B validator flagged a correct restriction as
# "overstated" in 2 of 2 runs, so its verdict is shown as a warning and the rule checks decide.
# VALIDATOR_BLOCKING=true makes unsupported/overstated claims hold the report back.
BLOCKING = os.environ.get("VALIDATOR_BLOCKING", "false").strip().lower() == "true"


def draft_from_report(report: Report) -> Draft | None:
    """Only what the model must judge: ingredients with a positive claim, and the evidence they cite."""
    ingredients = []
    for ing in report.ingredients:
        has_claim = (ing.regulatory.status in ("prohibited", "restricted") or ing.toxicology.hazards
                     or ing.toxicology.concern_level in ("low", "moderate", "high"))
        if not has_claim:
            continue
        ingredients.append({
            "ingredient_id": ing.ingredient_id,
            "concentration_percent": ing.concentration_percent,
            "regulatory": {
                "status": ing.regulatory.status,
                "conditions": [c.model_dump(include={"entry", "type", "requirement", "result", "reason"})
                               for c in ing.regulatory.conditions],
                "explanation": ing.regulatory.explanation,
                "evidence_ids": ing.regulatory.evidence_ids,
            },
            "toxicology": {
                "hazards": [h.model_dump(include={"label", "evidence_ids"}) for h in ing.toxicology.hazards],
                "explanation": ing.toxicology.explanation,
                "evidence_ids": ing.toxicology.evidence_ids,
            },
        })
    cf = report.cruelty_free
    # not_verified / not_assessed report that nothing was found: not a claim, so not audited
    # (observed: the model flagged "no certification found" as unsupported).
    has_cf_claim = cf.status in ("verified", "claimed", "conflicting")
    if not ingredients and not has_cf_claim:
        return None
    with_text = {s.evidence_id for s in report.sources if s.excerpt}
    for i in ingredients:  # evidence without text cannot be judged (a rule check reports it)
        for part in (i["regulatory"], i["toxicology"]):
            part["evidence_ids"] = [e for e in part["evidence_ids"] if e in with_text]
    cited = {e for i in ingredients for e in i["regulatory"]["evidence_ids"] + i["toxicology"]["evidence_ids"]}
    if has_cf_claim:
        cited |= set(cf.evidence_ids) & with_text
    return Draft(
        # Claims such as "rinse-off only, this product is leave-on" depend on the product type.
        product=report.product.model_dump(include={"category", "exposure_type"}),
        ingredients=ingredients or [{"note": "no ingredient-level claims"}],
        cruelty_free=cf.model_dump(include={"status", "explanation", "evidence_ids", "certifications_found"})
        if has_cf_claim else {},
        sources=[s.model_dump(include={"evidence_id", "kind", "excerpt"}) for s in report.sources if s.evidence_id in cited],
    )


def validate_report(report: Report, version: str = "v5") -> ValidatedReport:
    """Run the validator agent on a built report and add its verdict as the `ai_validator` check.

    Unsupported or overstated claims fail the check: a warning by default, an error with
    VALIDATOR_BLOCKING=true. If the model cannot be reached the check is a failed warning:
    the rule checks still decide, so an outage does not block reports.
    """
    report = report.model_copy(deep=True)
    draft = draft_from_report(report)
    validator, issues, severity = None, [], "error" if BLOCKING else "warning"
    if draft is None:
        pass  # nothing positive to verify
    else:
        try:
            validator = validate_draft(draft, version)
            r = validator.result
            # The model may only judge claims that are in the report (observed: it invented
            # "The product is cruelty-free" when the report said no such thing).
            known_ids = {i.get("ingredient_id") for i in draft.ingredients}
            cited = {s.evidence_id for s in draft.sources}
            real = [c for c in r.claims if (c.agent == "ethics" and draft.cruelty_free)
                    or (c.agent != "ethics" and c.ingredient_id in known_ids)]
            issues = [f"{c.agent}{'/' + c.ingredient_id if c.ingredient_id else ''}: {c.verdict}. {c.reason}".strip()
                      for c in real if c.verdict != "supported"]
            issues += [f"evidence {e} does not state what it is cited for" for e in r.unsupported_evidence_ids if e in cited]
            if not r.claims and not r.valid:  # v1: no per-claim verdicts, only its own flag
                issues = r.issues or ["the validator rejected the report without a reason"]
        except (ValidatorError, llm.LLMError) as exc:
            severity, issues = "warning", [f"validator unavailable: {exc}"]
    checks = [c for c in report.validation.checks if c.name != AI_CHECK]
    checks.append(ValidationCheck(name=AI_CHECK, severity=severity, passed=not issues,
                                  description=AI_CHECK_DESCRIPTION, issues=issues))
    passed = all(c.passed for c in checks if c.severity == "error")
    report.validation = Validation(passed=passed, checks=checks)
    return ValidatedReport(status="completed" if passed else "needs_review", report=report, validator=validator)
