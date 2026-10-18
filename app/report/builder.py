"""POST /report/build: merges the agents' outputs into the report the app shows. Deterministic, no LLM.

Every claim gets evidence items with their text: annex entries from the regulatory corpus, CLP
rows or the toxicology agent's quotes, and the ethics agent's evidence details.
"""

from datetime import datetime, timezone

from app.common_schemas import Ingredient, ProductInput
from app.ethics.schemas import EthicsResponse
from app.regulatory.schemas import RegulatoryFinding
from app.report import sources as src
from app.report.checks import run_checks
from app.report.schemas import (
    CrueltyFree,
    EvidenceCoverage,
    HazardPart,
    IngredientReport,
    Overview,
    RegulatoryPart,
    Report,
    ReportProduct,
    ReportRequest,
    SourceRef,
    ToxicologyPart,
    Validation,
)
from app.toxicology.schemas import IngredientFinding as ToxFinding

CONFIDENCE_ORDER = ["low", "medium", "high"]
ETHICS_KIND = {"certification": "certification", "brand_claim": "brand_claim",
               "regulatory": "regulation", "third_party_report": "third_party"}

COVERAGE_DEFINITION = (
    "Ingredients with at least one cited regulatory or toxicology source (with its text) about that "
    "ingredient, divided by all listed ingredients. It measures how much evidence was found, not how "
    "safe the product is."
)

LIMITATIONS = [
    "Ingredient concentrations are not on the label, so limits that depend on concentration cannot be checked.",
    "A hazard classification describes the substance; consumer risk also depends on concentration and exposure.",
    "This report does not state that the product is safe, unsafe, legal or illegal, and is not medical advice.",
    "Only ingredients covered by the current corpus are assessed; the others are marked as not assessed.",
    "Brand claims and independent certifications are reported as separate kinds of evidence.",
]


class _Evidence:
    """Collects evidence items, one per evidence_id, in citation order."""

    def __init__(self) -> None:
        self.items: dict[str, SourceRef] = {}

    def add(self, evidence_id: str, source_id: str, kind: str, excerpt: str) -> str:
        if evidence_id not in self.items:
            info = src.registry().get(source_id)
            self.items[evidence_id] = SourceRef(
                evidence_id=evidence_id, source_id=source_id, kind=kind,
                excerpt="" if src.is_placeholder(excerpt) else excerpt.strip(),
                title=info.title if info else None, publisher=info.publisher if info else None,
                date=info.date if info else None, url=info.url if info else None, in_corpus=info is not None,
            )
        return evidence_id


def _regulatory(ing: Ingredient, f: RegulatoryFinding | None, ev: _Evidence) -> RegulatoryPart:
    if f is None:
        return RegulatoryPart(status="not_assessed", compliance_check="not_applicable",
                              explanation="Regulatory analysis not available for this scan.")
    ids = [ev.add(f"{e.source_id}#{e.entry}", e.source_id, "regulation", src.annex_text(e.source_id, e.entry))
           for e in f.entries]
    for sid in f.sources:
        if any(sid == e.source_id for e in f.entries):
            continue  # already cited entry by entry
        if sid == "regulatory_scope":
            ids.append(ev.add(f"regulatory_scope#{f.ingredient}", sid, "coverage_list", src.scope_text(f.ingredient)))
        else:
            ids.append(ev.add(sid, sid, "regulation", src.article_text(sid)))
    return RegulatoryPart(status=f.regulatory_status, compliance_check=f.compliance_check,
                          entries=[f"{e.annex}/{e.entry}" for e in f.entries], conditions=f.conditions,
                          explanation=f.explanation, evidence_ids=list(dict.fromkeys(ids)))


def _toxicology(ing: Ingredient, f: ToxFinding | None, ev: _Evidence) -> ToxicologyPart:
    if f is None:
        return ToxicologyPart(concern_level="insufficient_evidence",
                              explanation="Toxicology analysis not available for this scan.")

    def text_for(source_id: str, quote: str | None) -> str:
        if not src.is_placeholder(quote):
            return quote
        return src.clp_text(f.ingredient) if source_id == "clp_test_ingredients" else ""

    hazards = []
    for h in f.hazards:
        eid = ev.add(f"{h.source_id}#{f.ingredient}", h.source_id, "toxicology", text_for(h.source_id, h.quote))
        hazards.append(HazardPart(endpoint=h.endpoint, label=h.classification, evidence_ids=[eid]))
    ids = [i for h in hazards for i in h.evidence_ids]
    for sid in f.sources:
        ids.append(ev.add(f"{sid}#{f.ingredient}", sid, "toxicology", text_for(sid, None)))
    return ToxicologyPart(concern_level=f.concern_level, hazards=hazards, explanation=f.risk_interpretation,
                          evidence_ids=list(dict.fromkeys(ids)))


def _cruelty_free(e: EthicsResponse | None, ev: _Evidence) -> CrueltyFree:
    if e is None:
        return CrueltyFree(status="not_assessed", explanation="Cruelty-free analysis not available for this scan.",
                           brand_claim_found=False, evidence_confidence="low")
    ids = [ev.add(f"{item.source_id}#{n}", item.source_id, ETHICS_KIND[item.type], f"{item.source}: {item.detail}")
           for n, item in enumerate(e.evidence, start=1)]
    return CrueltyFree(
        status=e.status.lower(), explanation=e.status_reason,
        brand_claim_found=any(item.type == "brand_claim" for item in e.evidence),
        certifications_found=[c.name for c in e.certifications_found],
        certifications_checked=e.certifications_checked, conflicts=e.conflicts,
        evidence_ids=ids, evidence_confidence=e.evidence_confidence,
    )


def _ingredient(ing: Ingredient, reg: RegulatoryFinding | None, tox: ToxFinding | None, ev: _Evidence) -> IngredientReport:
    regulatory = _regulatory(ing, reg, ev)
    toxicology = _toxicology(ing, tox, ev)
    cited = [ev.items[i] for i in regulatory.evidence_ids + toxicology.evidence_ids]
    confidences = [f.evidence_confidence for f in (reg, tox) if f is not None]
    concentration = getattr(ing, "concentration_percent", None)
    missing = list(dict.fromkeys([*(reg.missing_information if reg else []), *(tox.missing_information if tox else [])]))
    if concentration is None and any(c.type == "max_concentration" for c in regulatory.conditions):
        missing = list(dict.fromkeys([*missing, "concentration"]))
    return IngredientReport(
        position=ing.position, ingredient_id=ing.normalized, raw=ing.raw, matched=ing.matched,
        concentration_percent=concentration,
        covered=any(s.excerpt and s.in_corpus for s in cited),
        regulatory=regulatory, toxicology=toxicology, missing_information=missing,
        evidence_confidence=min(confidences, key=CONFIDENCE_ORDER.index) if confidences else "low",
    )


def _product(p: ProductInput) -> ReportProduct:
    return ReportProduct(name=p.product.name, brand=p.product.brand, barcode=p.product.barcode,
                         category=p.product.category or None, exposure_type=p.product.exposure_type)


def build_report(req: ReportRequest, now: datetime | None = None) -> Report:
    ev = _Evidence()
    reg = {f.position: f for f in req.regulatory.findings} if req.regulatory else {}
    tox = {f.position: f for f in req.toxicology.findings} if req.toxicology else {}
    ingredients = [_ingredient(i, reg.get(i.position), tox.get(i.position), ev)
                   for i in sorted(req.product_input.ingredients, key=lambda i: i.position)]
    cruelty_free = _cruelty_free(req.ethics, ev)

    def count(pred) -> int:
        return sum(1 for i in ingredients if pred(i))

    covered = count(lambda i: i.covered)
    outputs = {"regulatory": req.regulatory, "toxicology": req.toxicology, "ethics": req.ethics}
    report = Report(
        generated_at=now or datetime.now(timezone.utc),
        input_source=req.product_input.source,
        product=_product(req.product_input),
        needs_review=req.product_input.needs_review,
        overview=Overview(
            total_ingredients=len(ingredients),
            prohibited=count(lambda i: i.regulatory.status == "prohibited"),
            restricted=count(lambda i: i.regulatory.status == "restricted"),
            conditions_not_met=count(lambda i: i.regulatory.status == "restricted" and i.regulatory.compliance_check == "not_satisfied"),
            conditions_unknown=count(lambda i: i.regulatory.status == "restricted" and i.regulatory.compliance_check == "unknown"),
            concentration_unknown=count(lambda i: "concentration" in i.missing_information),
            hazard_classified=count(lambda i: bool(i.toxicology.hazards)),
            not_assessed=count(lambda i: i.regulatory.status == "not_assessed"),
        ),
        ingredients=ingredients,
        cruelty_free=cruelty_free,
        evidence_coverage=EvidenceCoverage(covered=covered, total=len(ingredients),
                                           percent=round(100 * covered / max(len(ingredients), 1)),
                                           definition=COVERAGE_DEFINITION),
        sources=list(ev.items.values()),
        validation=Validation(passed=True, checks=[]),
        prompt_versions={name: out.prompt_version if out else None for name, out in outputs.items()},
        warnings=list(dict.fromkeys([*req.product_input.warnings, *(w for o in outputs.values() if o for w in o.warnings)])),
        limitations=LIMITATIONS,
    )
    checks = run_checks(req, report)
    report.validation = Validation(passed=all(c.passed for c in checks if c.severity == "error"), checks=checks)
    return report
