"""Toxicology agent.

For each ingredient:
1. Gate (code): unrecognised ingredients are not assessed.
2. Retrieve (RAG): the CLP passage and the SCCS opinion passages for the ingredient.
3. Rules (code, app/toxicology/rules.py): hazards from the CLP passage, concern level, a default text.
4. Interpret (LLM, live mode only, only when SCCS passages were retrieved): SCCS findings with exact
   quotes, and the risk interpretation, from the passages only.
5. Validate (code): citations must be retrieved passages, quotes must appear word for word in them,
   labels may only state the quantities and product types of their quote and must agree with it on
   concern / no concern, no safety verdict wording (a label opening with "Safe" / "Not safe" is reworded),
   and the risk interpretation may only give quantities from an accepted quote. If every SCCS finding
   is rejected, the text has nothing behind it: retry. One retry, then the rule result (keeping the
   findings that passed every check, with their labels instead of the model's text).
   The LLM cannot lower the concern level.

mode="rules" skips step 4 (no credits): what the tests and TOXICOLOGY_MODE=mock use.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, ValidationError, field_validator

from app.common.llm import ChatFn, LLMError, Prompt, chat_function, model_name, parse_json_object
from app.common.llm import load_prompt as load_agent_prompt
from app.common_schemas import Ingredient, Product, ProductInput
from app.toxicology import rules
from app.toxicology.retrieval import SCCS, Passage, RetrievalError, search_toxicology
from app.toxicology.schemas import (Hazard, HazardEndpoint, IngredientFinding, ToxicologyResponse,
                                    ToxicologyRunStats)

DEFAULT_PROMPT = "v7"
# Same words as the report's no_safety_verdicts check (app/report/checks.py).
VERDICT_WORDS = re.compile(r"\b(safe|safely|unsafe|dangerous|harmful|toxic|non-toxic|causes? cancer|"
                           r"should be avoided|avoid|illegal)\b", re.I)


def load_prompt(version: str | None = None) -> Prompt:
    """prompts/toxicology/<version>.yaml; default from TOXICOLOGY_PROMPT_VERSION (v7)."""
    return load_agent_prompt("toxicology", version or os.environ.get("TOXICOLOGY_PROMPT_VERSION", DEFAULT_PROMPT))


# ---- what the LLM must return ---------------------------------------------------------
class LLMFinding(BaseModel):
    endpoint: HazardEndpoint
    finding: str
    evidence_id: str
    quote: str


class LLMOutput(BaseModel):
    sccs_findings: list[LLMFinding] = []
    risk_interpretation: str
    missing_information: list[str] = []
    evidence_ids: list[str]

    @field_validator("missing_information", "evidence_ids", mode="before")
    @classmethod
    def one_string_is_a_list(cls, v):
        # Qwen 7B often answers "concentration" instead of ["concentration"]: not worth a retry.
        return [s.strip() for s in v.split(";") if s.strip()] if isinstance(v, str) else v


OUTPUT_SCHEMA = json.dumps(
    {
        "sccs_findings": [{"endpoint": "sensitisation | skin_irritation | eye_irritation | carcinogenicity | "
                                       "mutagenicity | reproductive_toxicity | other",
                           "finding": "short label, max 12 words",
                           "evidence_id": "evidence_id of the SCCS passage",
                           "quote": "words copied exactly from that passage"}],
        "risk_interpretation": "string, 2-3 sentences",
        "missing_information": ["string"],
        "evidence_ids": ["evidence_id values from the EVIDENCE"],
    },
    indent=2,
)


def _fields(ingredient: Ingredient, product: Product, baseline: IngredientFinding, passages: list[Passage]) -> dict:
    conc = ingredient.concentration_percent
    clp = [h.classification for h in baseline.hazards]
    return {
        "product": json.dumps({"name": product.name, "category": product.category,
                               "exposure_type": product.exposure_type}, ensure_ascii=False),
        "ingredient": ingredient.normalized,
        "concentration": f"{conc} %" if conc is not None else "unknown (not provided on the label)",
        "clp": "; ".join(clp) if clp else ("no human-health classification" if baseline.concern_level == "none_identified"
                                           else "no CLP data in the corpus"),
        "evidence": "\n\n".join(f"[evidence_id: {p.evidence_id} | {p.metadata.get('source') or p.source_id} | {p.section}]\n{p.text}"
                                for p in passages),
        "output_schema": OUTPUT_SCHEMA,
    }


# ---- validation --------------------------------------------------------------------------
def _squash(s: str) -> str:
    s = re.sub(r"[‐-―]", "-", s).lower()
    s = re.sub(r"(?<!\S)[-•·▪]+(?!\S)", " ", s)  # list bullets are page layout, not words (salicylic acid 2.0 %)
    s = re.sub(r"(\d)\s+%", r"\1%", s)  # "2.0 %" = "2.0%"
    return " ".join(s.split())


# Product types and exposure routes a label may name; each one named must also be in the quote.
PRODUCT_TERMS = {
    "leave-on": r"leave[- ]?on", "rinse-off": r"rinse[- ]?off", "spray": r"spray", "hair": r"hair",
    "face": r"\bfac(e|ial)\b", "body": r"\bbody\b", "lip": r"\blips?\b", "oral": r"\b(oral|mouth|toothpaste)",
    "eye": r"\beyes?\b", "children": r"\b(child|children|infant|baby|babies)\b", "nail": r"\bnails?\b",
    "sunscreen": r"\bsun", "deodorant": r"deodorant",
}
# Quantities only: chemical names are full of digits ("2-phenoxyethanol").
QUANTITY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%|ppm|mg|µg|ug|iu\b|percent)", re.I)


def _quantities(text: str) -> set[tuple[float, str]]:
    return {(float(n.replace(",", ".")), "%" if u.lower() == "percent" else u.lower()) for n, u in QUANTITY.findall(text)}


def _label_problem(label: str, quote: str) -> str | None:
    """The label may only say what its quote says: same quantities, same product types."""
    label, quote = _squash(label), _squash(quote)
    missing = sorted(f"{n:g} {u}" for n, u in _quantities(label) - _quantities(quote))
    if missing:
        return f"label quantity {missing} not in the quote"
    terms = [t for t, pattern in PRODUCT_TERMS.items() if re.search(pattern, label) and not re.search(pattern, quote)]
    if terms:
        return f"label names {terms}, the quote does not"
    return None


# A label that opens or ends with the SCCS verdict is reworded, not rejected (v7: 6 of 6 rejections were
# "Safe up to ..." / "Not safe in ...", then "... up to 1% safe"). The quote stays word for word; the
# rewording is logged. "not safe" is tried before "safe".
LEADING_VERDICT = [
    (re.compile(r"^(?:is\s+)?(?:not\s+(?:considered\s+)?safe|unsafe)\b", re.I), "SCCS concern"),
    (re.compile(r"^(?:is\s+)?(?:considered\s+)?safe(?:ly)?\b", re.I), "No SCCS concern"),
]
TRAILING_VERDICT = [
    (re.compile(r"[\s,;:-]+(?:is\s+)?(?:not\s+(?:considered\s+)?safe|unsafe)\.?$", re.I), "SCCS concern"),
    (re.compile(r"[\s,;:-]+(?:is\s+)?(?:considered\s+)?safe\.?$", re.I), "No SCCS concern"),
]
NO_CONCERN_LABEL = re.compile(r"\bno (?:sccs )?concern\b")
CONCERN_LABEL = re.compile(r"\bconcern\b|\bnot supported\b")


def _reword_verdict(label: str) -> str:
    label = label.strip()
    for pattern, replacement in LEADING_VERDICT:
        if pattern.match(label):
            return pattern.sub(replacement, label, count=1)
    for pattern, head in TRAILING_VERDICT:
        m = pattern.search(label)
        if m and m.start() > 0:
            rest = label[:m.start()].strip()
            return f"{head}: {rest[:1].lower()}{rest[1:]}"
    return label


def _direction_problem(label: str, quote: str) -> str | None:
    """"No concern" against a quote that states one, or the other way round."""
    label, concern = _squash(label), rules.sccs_concern(quote)
    if NO_CONCERN_LABEL.search(label):
        return "label says no concern, the quote states a concern" if concern else None
    if CONCERN_LABEL.search(label) and not concern:
        return "label states a concern, the quote does not"
    return None


def _check(out: LLMOutput, passages: list[Passage], stats: ToxicologyRunStats, name: str,
           attempt: int = 1, concentration: float | None = None) -> list[str]:
    """Problems that make the answer unusable (-> retry). A bad finding next to a good one is dropped, not retried."""
    by_id = {p.evidence_id: p for p in passages}
    problems = []
    if not out.evidence_ids:
        problems.append("'evidence_ids' must cite at least one evidence_id from the EVIDENCE")
    unknown = set(out.evidence_ids) - set(by_id)
    if unknown:
        problems.append(f"'evidence_ids' contains ids not in the EVIDENCE: {sorted(unknown)}")
    verdicts = sorted({m.lower() for m in VERDICT_WORDS.findall(out.risk_interpretation)})
    if verdicts:
        problems.append(f"risk_interpretation uses the forbidden word(s) {verdicts}. Rewrite it without them, even "
                        "when the SCCS uses them: e.g. 'the SCCS raised no concern up to 1 %'")
    if not out.risk_interpretation.strip() or len(out.risk_interpretation) > 700:
        problems.append("risk_interpretation must be 2-3 short sentences")

    # Each finding on its own first, then one per opinion among the valid ones: a wrong first finding
    # must not push out a correct second one.
    tag = f"{name} (attempt {attempt})"
    valid, reasons = [], []
    for f in out.sccs_findings:
        label = _reword_verdict(f.finding)
        if label != f.finding.strip():
            stats.llm_issues.append(f"{tag}: label reworded {f.finding!r} -> {label!r}")
            f.finding = label
        p = by_id.get(f.evidence_id)
        reason = None
        if p is None or p.doc_type != SCCS:
            reason = "evidence_id is not an SCCS passage of the EVIDENCE"
        elif len(f.quote.split()) < 5 or _squash(f.quote) not in _squash(p.text):
            reason = f"quote not found word for word in the passage; quote starts {f.quote.strip()[:70]!r}"
        elif VERDICT_WORDS.search(f.finding):
            reason = "finding label uses verdict wording"
        else:
            reason = _label_problem(f.finding, f.quote) or _direction_problem(f.finding, f.quote)
        if reason:
            stats.rejected_findings.append(f"{tag}: {f.finding!r} ({reason})")
            reasons.append(f"{f.finding!r}: {reason}")
        else:
            valid.append((f, p.source_id))
    kept, used_sources = [], set()
    for f, source_id in valid:
        if source_id in used_sources:  # the report shows one quote per opinion and ingredient
            stats.rejected_findings.append(f"{tag}: {f.finding!r} (second valid finding from the same opinion)")
        else:
            used_sources.add(source_id)
            kept.append(f)
    if out.sccs_findings and not kept:
        problems.append(f"every sccs_finding was rejected ({'; '.join(reasons)}). A label may only use the limits "
                        "and product types written in its own quote")

    # The text may only give numbers that an accepted quote (or the label's concentration) gives.
    allowed = set().union(*(_quantities(_squash(f.quote)) for f in kept))
    if concentration is not None:
        allowed.add((float(concentration), "%"))
    extra = sorted(f"{n:g} {u}" for n, u in _quantities(_squash(out.risk_interpretation)) - allowed)
    if extra:
        problems.append(f"risk_interpretation gives {extra}, which no accepted finding's quote gives. "
                        "Only use numbers from the quotes of your sccs_findings")
    out.sccs_findings = kept
    return problems


def _merge(baseline: IngredientFinding, out: LLMOutput, passages: list[Passage],
           text: str | None = None) -> IngredientFinding:
    by_id = {p.evidence_id: p for p in passages}
    sccs = [Hazard(endpoint=f.endpoint, classification=f"SCCS: {f.finding.strip()}",
                   source_id=by_id[f.evidence_id].source_id, quote=f.quote.strip()) for f in out.sccs_findings]
    level = baseline.concern_level
    if sccs:  # SCCS findings can raise the rule level, never lower it
        floor = "none_identified" if level == "insufficient_evidence" else level
        level = rules.highest([floor] + [rules.sccs_level(h.endpoint, h.quote) for h in sccs])
    missing = list(baseline.missing_information)
    for item in out.missing_information:
        item = item.strip().lower()
        if item and item not in missing and len(missing) < 6:
            missing.append(item)
    return baseline.model_copy(update={
        "hazards": baseline.hazards + sccs, "concern_level": level,
        "risk_interpretation": text or out.risk_interpretation.strip(), "missing_information": missing,
    })


def _interpret(ingredient: Ingredient, product: Product, baseline: IngredientFinding, passages: list[Passage],
               prompt: Prompt, chat: ChatFn, stats: ToxicologyRunStats, warnings: list[str]) -> IngredientFinding:
    messages = prompt.render(**_fields(ingredient, product, baseline, passages))
    best = None  # last answer with SCCS findings that passed every check
    for attempt in range(2):
        stats.llm_calls += 1
        try:
            answer = chat(messages, prompt.temperature, prompt.max_tokens)
        except Exception as e:  # network, auth, rate limit
            warnings.append(f"toxicology: LLM call failed for {ingredient.normalized} ({type(e).__name__}); rule result used")
            stats.fallbacks += 1
            return baseline
        try:
            out = LLMOutput.model_validate(parse_json_object(answer))
            problems = _check(out, passages, stats, ingredient.normalized, attempt + 1,
                              ingredient.concentration_percent)
        except ValidationError as e:
            fields = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:3])
            out, problems = None, [f"the answer does not match the schema ({fields})"]
        except ValueError as e:
            out, problems = None, [f"the answer is not a JSON object ({e})"]
        if not problems:
            return _merge(baseline, out, passages)
        if out is not None and out.sccs_findings:
            best = out
        stats.llm_issues += [f"{ingredient.normalized} (attempt {attempt + 1}): {p}" for p in problems]
        if out is None:  # show how the answer starts (cut off? text before the JSON?)
            stats.llm_issues[-1] += f" | answer starts: {answer.strip()[:120]!r}"
        if attempt == 0:
            stats.retries += 1
            messages = messages + [
                {"role": "assistant", "content": answer},
                {"role": "user", "content": "Your answer was invalid:\n- " + "\n- ".join(problems)
                 + "\nReturn the corrected JSON object only."},
            ]
    stats.fallbacks += 1
    if best is not None:
        # Only the text failed (salicylic acid, v7: its 0.5 % finding was valid, the text cited a rejected 2 %).
        # The validated labels replace the model's text: nothing in them is unchecked.
        warnings.append(f"toxicology: LLM interpretation invalid for {ingredient.normalized}; "
                        "validated SCCS findings kept with the rule text")
        labels = "; ".join(f.finding.strip() for f in best.sccs_findings)
        return _merge(baseline, best, passages, text=f"{baseline.risk_interpretation} SCCS findings: {labels}.")
    warnings.append(f"toxicology: LLM output invalid for {ingredient.normalized}; rule result used")
    return baseline


# ---- per ingredient ----------------------------------------------------------------------
def _assess(ingredient: Ingredient, product: Product, prompt: Prompt | None, chat: ChatFn | None,
            stats: ToxicologyRunStats, warnings: list[str]) -> IngredientFinding:
    if not ingredient.matched:
        return rules.not_assessed(ingredient, "Ingredient not recognised as an INCI name; no evidence retrieved.",
                                  "recognised INCI name")
    try:
        passages = search_toxicology(ingredient.normalized)
    except RetrievalError as e:
        warnings.append(f"toxicology: {e}")
        return rules.not_assessed(ingredient, "Toxicology evidence could not be retrieved.", "toxicology evidence")
    if not passages:
        return rules.apply_ocr_confidence(rules.not_assessed(
            ingredient, "No CLP classification or SCCS opinion for this ingredient in the corpus.",
            "evidence in toxicology corpus"), ingredient)

    finding = rules.baseline_finding(ingredient, passages)
    # The model reads the SCCS opinions; for a CLP row alone the rule text says everything.
    if chat is not None and any(p.doc_type == SCCS for p in passages):
        finding = _interpret(ingredient, product, finding, passages, prompt, chat, stats, warnings)
    return rules.apply_ocr_confidence(finding, ingredient)


def analyze(payload: ProductInput, mode: str = "live", chat: ChatFn | None = None,
            prompt: Prompt | None = None) -> ToxicologyResponse:
    """mode "live": retrieval + LLM + validation; "rules": retrieval + rules only (no LLM call)."""
    warnings = list(payload.warnings)
    if mode == "live":
        prompt = prompt or load_prompt()
        if chat is None:
            try:
                chat = chat_function()
            except LLMError as e:  # no usable model (e.g. token missing): rules instead of a 500
                warnings.append(f"toxicology: LLM unavailable ({e}); rule-based result only")
                mode = "rules"
    if mode != "live":
        chat = None
    stats = ToxicologyRunStats(mode="live" if chat else "rules", model=model_name() if chat else None,
                               retrieval_backend=os.environ.get("RETRIEVAL_BACKEND", "local"))
    workers = int(os.environ.get("TOXICOLOGY_MAX_PARALLEL", "4"))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        findings = list(pool.map(lambda i: _assess(i, payload.product, prompt, chat, stats, warnings),
                                 payload.ingredients))
    return ToxicologyResponse(prompt_version=prompt.version if chat else "rules", findings=findings,
                              warnings=warnings, run=stats)
