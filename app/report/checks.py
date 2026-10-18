"""Rule checks run on every report before it is shown (deterministic, no LLM).

Error-level checks decide `validation.passed`; n8n then answers needs_review instead of completed.
Warning-level checks are shown but do not hold the report back.
"""

import re

from app.report.schemas import IngredientReport, Report, ReportRequest, ValidationCheck
from app.report.sources import registry

# Wording the agents must not use: the project reports evidence, never a safety verdict.
VERDICT_WORDS = re.compile(
    r"\b(safe|unsafe|dangerous|harmful|toxic|non-toxic|causes? cancer|should be avoided|avoid|illegal)\b",
    re.IGNORECASE,
)


def _claim_evidence(ing: IngredientReport) -> list[tuple[str, list[str]]]:
    """(claim description, evidence ids) for every positive claim about one ingredient."""
    out = []
    if ing.regulatory.status in ("prohibited", "restricted"):
        out.append((f"regulatory/{ing.ingredient_id}: {ing.regulatory.status}", ing.regulatory.evidence_ids))
    for h in ing.toxicology.hazards:
        out.append((f"toxicology/{ing.ingredient_id}: {h.label}", h.evidence_ids))
    return out


def run_checks(req: ReportRequest, report: Report) -> list[ValidationCheck]:
    sources = {s.evidence_id: s for s in report.sources}
    reg_info = registry()
    checks: list[ValidationCheck] = []

    def add(name, severity, description, issues):
        checks.append(ValidationCheck(name=name, severity=severity, passed=not issues,
                                      description=description, issues=list(dict.fromkeys(issues))))

    # 1. All three agents answered.
    add("agents_present", "warning", "All three agents returned an output.",
        [f"{name} output missing" for name in ("regulatory", "toxicology", "ethics") if getattr(req, name) is None])

    # 2. Ingredient-level agents cover every ingredient exactly once (by label position).
    positions = sorted(i.position for i in req.product_input.ingredients)
    coverage = []
    for name in ("regulatory", "toxicology"):
        resp = getattr(req, name)
        if resp is None:
            continue
        got = sorted(f.position for f in resp.findings)
        if got != positions:
            missing = sorted(set(positions) - set(got))
            extra = sorted(set(got) - set(positions))
            dupes = sorted({p for p in got if got.count(p) > 1})
            if missing:
                coverage.append(f"{name}: no finding for label positions {missing}")
            if extra:
                coverage.append(f"{name}: findings for unknown positions {extra}")
            if dupes:
                coverage.append(f"{name}: positions {dupes} covered more than once")
    add("agent_coverage", "error", "Each agent covers every ingredient exactly once.", coverage)

    # 3. Every cited source is registered in the corpus.
    add("citations_known", "error", "Every cited source is registered in corpus/sources.csv.",
        [f"{s.evidence_id}: source '{s.source_id}' is not in corpus/sources.csv" for s in report.sources if not s.in_corpus])

    # 4. Cited sources are about the ingredient they support.
    subject = []
    for ing in report.ingredients:
        for eid in ing.regulatory.evidence_ids + ing.toxicology.evidence_ids:
            info = reg_info.get(sources[eid].source_id) if eid in sources else None
            if info and info.ingredients is not None and ing.ingredient_id not in info.ingredients:
                subject.append(f"{ing.ingredient_id} cites {eid}, a source about {', '.join(sorted(info.ingredients))}")
    add("citation_subject", "warning", "Cited sources are about the ingredient they support.", subject)

    # 5. Every claim's evidence has its text (no placeholders), so it can be checked.
    excerpt_issues = []
    for ing in report.ingredients:
        for claim, ids in _claim_evidence(ing):
            for eid in ids:
                if eid in sources and not sources[eid].excerpt:
                    excerpt_issues.append(f"{claim}: evidence {eid} has no text (missing or placeholder quote)")
    for eid in report.cruelty_free.evidence_ids:
        if eid in sources and not sources[eid].excerpt:
            excerpt_issues.append(f"cruelty-free: evidence {eid} has no text")
    add("excerpts_available", "error", "Every claim's evidence has its source text.", excerpt_issues)

    # 6. Every claim cites evidence.
    backing = []
    for ing in report.ingredients:
        for claim, ids in _claim_evidence(ing):
            if not ids:
                backing.append(f"{claim}: no evidence cited")
        if ing.toxicology.concern_level in ("low", "moderate", "high") and not ing.toxicology.evidence_ids:
            backing.append(f"toxicology/{ing.ingredient_id}: concern '{ing.toxicology.concern_level}' without evidence")
    cf = report.cruelty_free
    kinds = {sources[e].kind for e in cf.evidence_ids if e in sources}
    if cf.status == "verified" and "certification" not in kinds:
        backing.append("cruelty-free: 'verified' needs an independent certification source")
    if cf.status == "claimed" and "brand_claim" not in kinds:
        backing.append("cruelty-free: 'claimed' needs a cited brand claim")
    if cf.status == "conflicting" and not cf.conflicts:
        backing.append("cruelty-free: 'conflicting' without listing the conflict")
    add("claims_have_evidence", "error", "Statuses, hazards and cruelty-free claims cite evidence.", backing)

    # 7. A concentration limit cannot be judged without the concentration.
    concentration = []
    for ing in report.ingredients:
        if ing.concentration_percent is None:
            for c in ing.regulatory.conditions:
                if c.type == "max_concentration" and c.result in ("satisfied", "not_satisfied"):
                    concentration.append(f"regulatory/{ing.ingredient_id} {c.entry}: concentration unknown, "
                                         f"but the limit is marked {c.result}")
    add("missing_concentration", "error", "Concentration limits stay unknown when the concentration is unknown.", concentration)

    # 8. No safety verdicts in what the user reads.
    texts = []
    for ing in report.ingredients:
        texts.append((f"regulatory/{ing.ingredient_id}", ing.regulatory.explanation))
        texts += [(f"regulatory/{ing.ingredient_id} {c.entry}", c.reason) for c in ing.regulatory.conditions]
        texts.append((f"toxicology/{ing.ingredient_id}", ing.toxicology.explanation))
    texts.append(("cruelty-free", cf.explanation))
    wording = []
    for where, text in texts:
        words = sorted({m.group(0).lower() for m in VERDICT_WORDS.finditer(text or "")})
        if words:
            wording.append(f"{where}: uses verdict wording ({', '.join(words)})")
    add("no_safety_verdicts", "error", "No 'safe', 'toxic', 'avoid' or 'illegal' verdicts in explanations.", wording)

    return checks
