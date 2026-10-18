"""Live regulatory agent.

For each ingredient:
1. Gate (code): unrecognised or out-of-scope ingredients are not assessed.
2. Retrieve (Haroun's service, or the local placeholder): regulation passages for the ingredient.
3. Status (code): Annex II -> prohibited, Annex III-VI -> restricted, nothing -> no restriction found.
4. Interpret (LLM): only for restricted ingredients. The LLM reads each condition of the
   retrieved entries against the product and explains the result.
5. Validate (code): schema, condition coverage, citations, wording; safety rules override the
   LLM where needed; one retry, then a conservative fallback.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, ValidationError

from app.common_schemas import Ingredient, Product, ProductInput
from app.regulatory import rules
from app.regulatory.kb import load_kb
from app.common.llm import ChatFn, LLMError, Prompt, chat_function, model_name, parse_json_object
from app.common.llm import load_prompt as load_agent_prompt
from app.regulatory.retrieval import Passage, RetrievalError, search_regulation
from app.regulatory.schemas import (
    AgentRunStats,
    ConditionCheck,
    ConditionResult,
    ProductContext,
    RegulatoryFinding,
    RegulatoryResponse,
)


def load_prompt(version: str | None = None) -> Prompt:
    """prompts/regulatory/<version>.yaml; default from REGULATORY_PROMPT_VERSION (v4)."""
    return load_agent_prompt("regulatory",version or os.environ.get("REGULATORY_PROMPT_VERSION", "v4"))


FORBIDDEN_WORDS = re.compile(r"\b(safe|safely|unsafe|illegal|unlawful|dangerous|toxic|harmful)\b", re.I)


# ---- what the LLM must return ---------------------------------------------------------
class LLMCondition(BaseModel):
    index: int
    result: ConditionResult
    reason: str


class LLMOutput(BaseModel):
    regulatory_status: str
    conditions: list[LLMCondition]
    explanation: str
    missing_information: list[str] = []
    evidence_ids: list[str]


OUTPUT_SCHEMA = json.dumps(
    {
        "regulatory_status": "prohibited | restricted",
        "conditions": [{"index": 0, "result": "satisfied | not_satisfied | unknown | not_applicable", "reason": "string"}],
        "explanation": "string, max 2 sentences",
        "missing_information": ["string"],
        "evidence_ids": ["source_id values from the EVIDENCE"],
    },
    indent=2,
)


# ---- prompt fields ------------------------------------------------------------------------
def _concentration(ingredient: Ingredient) -> float | None:
    return ingredient.concentration_percent


def _fields(ingredient: Ingredient, product: Product, status: str, passages: list[Passage],
            conditions: list[ConditionCheck]) -> dict[str, str]:
    conc = _concentration(ingredient)
    entries = ", ".join(f"Annex {p.annex} entry {p.entry}" for p in passages)
    return {
        "product": json.dumps({"name": product.name, "category": product.category,
                               "exposure_type": product.exposure_type, "labels": product.labels}, ensure_ascii=False),
        "ingredient": f"{ingredient.normalized} (position {ingredient.position} in the ingredient list)",
        "concentration": f"{conc} %" if conc is not None else "unknown (not provided on the label)",
        "status": f"{status} ({entries})",
        "evidence": "\n\n".join(f"[evidence_id: {p.source_id} | Annex {p.annex} entry {p.entry}]\n{p.text}"
                                for p in passages),
        "conditions": "\n".join(
            f"[{i}] ({c.entry}, {c.type}) {c.requirement}"
            + (f"\n    -> already decided by rule: {c.result}. {c.reason}" if c.result != "unknown" else "")
            for i, c in enumerate(conditions)),
        "output_schema": OUTPUT_SCHEMA,
    }


# ---- validation --------------------------------------------------------------------------
def _decided_by_rule(c: ConditionCheck, has_conc: bool) -> bool:
    """Conditions whose result the safety rules fix anyway: a skipped one can be filled in by code."""
    return c.result != "unknown" or (c.type == "max_concentration" and not has_conc) or c.type == "labelling"


def _fill_skipped(out: LLMOutput, baseline: RegulatoryFinding, has_conc: bool, name: str, stats: AgentRunStats) -> None:
    given = {c.index for c in out.conditions}
    for i, c in enumerate(baseline.conditions):
        if i not in given and _decided_by_rule(c, has_conc):
            out.conditions.append(LLMCondition(index=i, result=c.result, reason=c.reason))
            stats.overrides.append(f"{name} [{i}] skipped by the LLM, filled by rule ('{c.result}')")


def _check(out: LLMOutput, n_conditions: int, allowed_ids: set[str]) -> list[str]:
    problems = []
    if sorted(c.index for c in out.conditions) != list(range(n_conditions)):
        problems.append(f"'conditions' must contain exactly one item for each index 0..{n_conditions - 1}")
    if not out.evidence_ids:
        problems.append("'evidence_ids' must cite at least one evidence_id from the EVIDENCE")
    unknown_ids = set(out.evidence_ids) - allowed_ids
    if unknown_ids:
        problems.append(f"'evidence_ids' contains ids not in the EVIDENCE: {sorted(unknown_ids)}")
    if FORBIDDEN_WORDS.search(out.explanation):
        problems.append("the explanation must not call the product or ingredient safe, unsafe, illegal, dangerous or toxic")
    if not out.explanation.strip() or len(out.explanation) > 600:
        problems.append("the explanation must be 1-2 short sentences")
    return problems


def _merge(ingredient: Ingredient, product: Product, baseline: RegulatoryFinding, out: LLMOutput,
           stats: AgentRunStats) -> RegulatoryFinding:
    by_index = {c.index: c for c in out.conditions}
    has_conc = _concentration(ingredient) is not None
    merged: list[ConditionCheck] = []
    for i, base in enumerate(baseline.conditions):
        llm = by_index[i]
        result, reason = llm.result, llm.reason.strip() or base.reason
        # Safety rules: these beat the LLM.
        if base.type == "max_concentration" and not has_conc and result != "unknown":
            stats.overrides.append(f"{ingredient.normalized} [{i}] concentration unknown -> 'unknown' (LLM said '{result}')")
            result, reason = "unknown", rules.NO_CONCENTRATION
        if base.type == "labelling" and base.result != "unknown" and result != base.result:
            # e.g. a fragrance allergen named in the ingredient list (rules.LISTED_ABOVE_THRESHOLD)
            stats.overrides.append(f"{ingredient.normalized} [{i}] labelling decided by rule -> '{base.result}' (LLM said '{result}')")
            result, reason = base.result, base.reason
        elif base.type == "labelling" and base.result == "unknown" and result in ("satisfied", "not_satisfied"):
            stats.overrides.append(f"{ingredient.normalized} [{i}] label text not available -> 'unknown' (LLM said '{result}')")
            result, reason = "unknown", "The label text is not available to check the required wording."
        if base.type == "max_concentration" and has_conc and base.result != "unknown" and result != base.result:
            stats.overrides.append(f"{ingredient.normalized} [{i}] concentration limit decided by rule -> '{base.result}' (LLM said '{result}')")
            result, reason = base.result, base.reason
        if base.type == "product_type" and base.result != "unknown" and result != base.result:
            stats.overrides.append(f"{ingredient.normalized} [{i}] product type decided by rule -> '{base.result}' (LLM said '{result}')")
            result, reason = base.result, base.reason
        merged.append(base.model_copy(update={"result": result, "reason": reason}))

    missing = rules.missing_from(merged, product)
    for item in out.missing_information:
        item = item.strip().lower()
        if item and item not in missing and len(missing) < 6:
            missing.append(item)
    return baseline.model_copy(update={
        "conditions": merged,
        "compliance_check": rules.compliance_from(baseline.regulatory_status, merged),
        "explanation": out.explanation.strip(),
        "missing_information": missing,
        "sources": sorted(set(out.evidence_ids)),
    })


def _interpret(ingredient: Ingredient, product: Product, baseline: RegulatoryFinding, passages: list[Passage],
               prompt: Prompt, chat: ChatFn, stats: AgentRunStats, warnings: list[str]) -> RegulatoryFinding:
    messages = prompt.render(**_fields(ingredient, product, baseline.regulatory_status, passages, baseline.conditions))
    allowed = {p.source_id for p in passages}
    for attempt in range(2):
        stats.llm_calls += 1
        try:
            answer = chat(messages, prompt.temperature, prompt.max_tokens)
        except Exception as e:  # network, auth, rate limit
            warnings.append(f"regulatory: LLM call failed for {ingredient.normalized} ({type(e).__name__}); conservative result used")
            stats.fallbacks += 1
            return baseline
        try:
            out = LLMOutput.model_validate(parse_json_object(answer))
            _fill_skipped(out, baseline, _concentration(ingredient) is not None, ingredient.normalized, stats)
            problems = _check(out, len(baseline.conditions), allowed)
        except (ValueError, ValidationError) as e:
            out, problems = None, [f"the answer is not valid JSON matching the schema ({str(e).splitlines()[0]})"]
        if out is not None and out.regulatory_status.strip().lower() != baseline.regulatory_status:
            stats.status_disagreements += 1  # status always comes from the retrieved annex
        if not problems:
            return _merge(ingredient, product, baseline, out, stats)
        if attempt == 0:
            stats.retries += 1
            messages = messages + [
                {"role": "assistant", "content": answer},
                {"role": "user", "content": "Your answer was invalid:\n- " + "\n- ".join(problems)
                 + "\nReturn the corrected JSON object only."},
            ]
    stats.fallbacks += 1
    warnings.append(f"regulatory: LLM output invalid for {ingredient.normalized}; conservative result used")
    return baseline


# ---- per ingredient ----------------------------------------------------------------------
def _assess(ingredient: Ingredient, product: Product, prompt: Prompt, chat: ChatFn, stats: AgentRunStats,
            warnings: list[str]) -> RegulatoryFinding:
    if not ingredient.matched:
        return rules.not_assessed(ingredient, "Ingredient not recognised as an INCI name; no regulatory evidence retrieved.",
                                  "recognised INCI name")
    canonical = load_kb().canonical(ingredient.normalized)
    if canonical is None:
        return rules.apply_ocr_confidence(
            rules.not_assessed(ingredient, "This ingredient is not covered by the current regulatory corpus.",
                               "evidence in regulatory corpus"), ingredient)
    try:
        passages = search_regulation(canonical, product.exposure_type)
    except RetrievalError as e:
        warnings.append(f"regulatory: {e}")
        return rules.not_assessed(ingredient, "Regulatory evidence could not be retrieved.", "regulatory evidence")
    if not passages:
        return rules.apply_ocr_confidence(rules.no_restriction(ingredient), ingredient)

    baseline = rules.baseline_finding(ingredient, product, [p.to_row() for p in passages])
    # The model interprets conditions the rules leave open; when the rules decide all of them, it is not called.
    if baseline.regulatory_status == "restricted" and any(c.result == "unknown" for c in baseline.conditions):
        baseline = _interpret(ingredient, product, baseline, passages, prompt, chat, stats, warnings)
    return rules.apply_ocr_confidence(baseline, ingredient)


def analyze(payload: ProductInput, chat: ChatFn | None = None, prompt: Prompt | None = None) -> RegulatoryResponse:
    prompt = prompt or load_prompt()
    if chat is None:
        try:
            chat = chat_function()
        except LLMError as e:
            # No usable model (e.g. token missing): answer with the rules instead of a 500.
            from app.regulatory.mock import build_mock_response

            resp = build_mock_response(payload)
            resp.warnings.append(f"regulatory: LLM unavailable ({e}); rule-based result only")
            return resp
    stats = AgentRunStats(mode="live", model=model_name(), retrieval_backend=os.environ.get("RETRIEVAL_BACKEND", "local"))
    warnings = list(payload.warnings)
    workers = int(os.environ.get("REGULATORY_MAX_PARALLEL", "4"))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        findings = list(pool.map(lambda i: _assess(i, payload.product, prompt, chat, stats, warnings), payload.ingredients))
    return RegulatoryResponse(
        prompt_version=prompt.version,
        product_context=ProductContext(category=payload.product.category, exposure_type=payload.product.exposure_type),
        findings=findings,
        warnings=warnings,
        run=stats,
    )
