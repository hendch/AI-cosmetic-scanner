"""Deterministic rules of the regulatory agent.

Code, not the LLM, decides:
- the gate (unrecognised / out-of-scope ingredients are not assessed),
- the regulatory status (from the annex of the retrieved entries),
- the compliance summary (computed from the condition results),
- the safety invariants (unknown concentration stays unknown, prohibited is never softened,
  only retrieved source_ids can be cited).

The same functions build a conservative baseline finding, used by the mock and as the
fallback when the LLM output is invalid.
"""

import re

from app.common_schemas import Ingredient, Product
from app.regulatory.kb import SCOPE_SOURCE_ID, AnnexRow
from app.regulatory.schemas import (
    AnnexEntry,
    ComplianceCheck,
    ConditionCheck,
    RegulatoryFinding,
    RegulatoryStatus,
)

OCR_CONFIDENCE_THRESHOLD = 0.8
OCR_NOTE = "ingredient name from OCR, unverified"
NO_CONCENTRATION = "Concentration is not provided on the label."


# ---- gate --------------------------------------------------------------------------
def not_assessed(ingredient: Ingredient, reason: str, missing: str) -> RegulatoryFinding:
    return RegulatoryFinding(
        position=ingredient.position,
        ingredient=ingredient.normalized,
        matched=ingredient.matched,
        regulatory_status="not_assessed",
        compliance_check="not_applicable",
        explanation=reason,
        missing_information=[missing],
        evidence_confidence="low",
    )


def no_restriction(ingredient: Ingredient) -> RegulatoryFinding:
    return RegulatoryFinding(
        position=ingredient.position,
        ingredient=ingredient.normalized,
        matched=ingredient.matched,
        regulatory_status="no_restriction_found",
        compliance_check="not_applicable",
        explanation=(
            "No entry for this ingredient was found in Annexes II to VI of the consolidated "
            "regulation checked. It is not prohibited or restricted by these annexes; the "
            "product's safety assessment still applies."
        ),
        evidence_confidence="high",
        sources=[SCOPE_SOURCE_ID],
    )


# ---- status and compliance ---------------------------------------------------------
def status_from_rows(rows: list[AnnexRow]) -> RegulatoryStatus:
    return "prohibited" if any(r.annex == "II" for r in rows) else "restricted"


def compliance_from(status: RegulatoryStatus, conditions: list[ConditionCheck]) -> ComplianceCheck:
    if status == "prohibited":
        return "not_satisfied"
    if status in ("no_restriction_found", "not_assessed"):
        return "not_applicable"
    results = {c.result for c in conditions}
    if "not_satisfied" in results:
        return "not_satisfied"
    if "unknown" in results:
        return "unknown"
    return "satisfied"


def entries_from_rows(rows: list[AnnexRow]) -> list[AnnexEntry]:
    return [AnnexEntry(annex=r.annex, entry=r.entry, source_id=r.source_id) for r in rows]


# ---- product-type matching ---------------------------------------------------------
# Small LLMs misread exclusion lists ("Other products except body lotion, ..."), so the
# matching of the product category to the lettered items of an entry is done here.
_STOP = {"product", "products", "and", "or", "the", "of", "in", "for", "form", "with", "use", "other", "a", "an"}
_SYNONYMS = {"shampoo": "hair", "conditioner": "hair", "hair": "hair", "cream": "cream", "serum": "serum",
             "toothpaste": "toothpaste", "mouthwash": "mouthwash", "deodorant": "deodorant", "spray": "spray",
             "aerosol": "aerosol", "lipstick": "lip", "balm": "balm"}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())
    out = set()
    for w in words:
        if w in _STOP:
            continue
        out.add(w)
        if w in _SYNONYMS:
            out.add(_SYNONYMS[w])
        if w.endswith("s") and len(w) > 3:
            out.add(w[:-1])
    return out


def _split_items(req: str) -> list[tuple[str, str]]:
    """'(a) X (b) Y' or 'a) X b) Y' -> [('a', 'X'), ('b', 'Y')]; no letters -> [('', req)]."""
    parts = re.split(r"(?:^|\s)\(?([a-h])\)\s+", " " + req.strip())
    if len(parts) < 3:
        return [("", req.strip())]
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def _item_matches(item: str, cat: set[str], exposure: str | None) -> bool | None:
    """True/False if the item clearly does or does not cover the product; None for catch-all items."""
    text = item.lower()
    text = re.split(r",?\s*including\b", text)[0]  # "including spray products" widens, ignore
    excluded: set[str] = set()
    for marker in (r"\bexcept\b", r"\bexcluding\b", r"with the exception of"):
        m = re.split(marker, text, maxsplit=1)
        if len(m) == 2:
            text, excl = m
            excluded = set().union(*[_tokens(x) for x in re.split(r",|\band\b", excl) if x.strip()])
    if excluded & cat:
        return False
    both = "rinse-off" in text and "leave-on" in text  # "leave-on and rinse-off products": no restriction
    if not both and "rinse-off" in text and exposure == "leave_on":
        return False
    if not both and "leave-on" in text and exposure == "rinse_off":
        return False
    core = text.replace("rinse-off", "").replace("leave-on", "")
    alternatives = [_tokens(x) for x in re.split(r",|\band\b|\bor\b", core) if _tokens(x)]
    if not alternatives:
        return None  # "Other products", "Other leave-on and rinse-off products": catch-all
    return any(alt <= cat for alt in alternatives)


def match_product_type(req: str, product: Product) -> tuple[str | None, bool | None]:
    """Returns (matching item letter or '' for single-item entries, matched?) or (None, None) if unknown."""
    if not product.category:
        return None, None
    cat = _tokens(product.category)
    items = _split_items(req)
    explicit = [(letter, _item_matches(text, cat, product.exposure_type)) for letter, text in items]
    for letter, ok in explicit:
        if ok is True:
            return letter, True
    for letter, ok in explicit:
        if ok is None:
            return letter, True  # catch-all item applies when no explicit item matched
    return None, False


# ---- baseline conditions (no interpretation) ---------------------------------------
def _product_type_condition(row: AnnexRow, product: Product) -> ConditionCheck:
    req = row.product_type_body_parts
    if req.strip().lower() == "rinse-off products":
        if product.exposure_type == "rinse_off":
            result, reason = "satisfied", "The product is a rinse-off product."
        elif product.exposure_type == "leave_on":
            result, reason = "not_satisfied", "The product is a leave-on product; the entry allows rinse-off products only."
        else:
            result, reason = "unknown", "Whether the product is leave-on or rinse-off is not known."
        return ConditionCheck(entry=row.ref, type="product_type", requirement=req, result=result, reason=reason)

    letter, matched = match_product_type(req, product)
    if matched is None:
        result, reason = "unknown", "The product category is not known, so it cannot be matched to the product types of the entry."
    elif matched:
        item = f"item ({letter})" if letter else "the product type"
        result, reason = "satisfied", f"The product ({product.category}) matches {item} of the entry; the limits of {item} apply."
    else:
        result, reason = "not_satisfied", f"The product ({product.category}) matches none of the product types allowed by the entry."
    return ConditionCheck(entry=row.ref, type="product_type", requirement=req, result=result, reason=reason)


def baseline_conditions(row: AnnexRow, product: Product) -> list[ConditionCheck]:
    """Conditions copied from the entry. Only checks that need no interpretation are decided."""
    if row.annex == "II":
        return []
    conditions: list[ConditionCheck] = []
    if row.product_type_body_parts and row.annex != "IV":
        conditions.append(_product_type_condition(row, product))
    if row.max_concentration:
        conditions.append(
            ConditionCheck(entry=row.ref, type="max_concentration", requirement=row.max_concentration,
                           result="unknown", reason=NO_CONCENTRATION)
        )
    if row.other_conditions:
        conditions.append(
            ConditionCheck(entry=row.ref, type="usage", requirement=row.other_conditions,
                           result="unknown", reason="Not checked against the product information.")
        )
    if row.warnings:
        conditions.append(
            ConditionCheck(entry=row.ref, type="labelling", requirement=row.warnings,
                           result="unknown", reason="The label text is not available to check the required wording.")
        )
    return conditions


def missing_from(conditions: list[ConditionCheck], product: Product) -> list[str]:
    missing: list[str] = []
    for c in conditions:
        if c.result != "unknown":
            continue
        item = {
            "max_concentration": "concentration",
            "labelling": "label text",
            "population": "target population",
        }.get(c.type)
        if c.type == "product_type":
            item = "product type" if product.exposure_type is None else "product category match"
        if item and item not in missing:
            missing.append(item)
    return missing


def baseline_explanation(status: RegulatoryStatus, rows: list[AnnexRow], compliance: ComplianceCheck) -> str:
    refs = ", ".join(f"Annex {r.annex} entry {r.entry}" for r in rows)
    if status == "prohibited":
        return f"Listed in {refs} of Regulation (EC) No 1223/2009: prohibited in cosmetic products."
    if compliance == "not_satisfied":
        return f"Allowed only under conditions ({refs}); at least one condition is not met for this product."
    if compliance == "unknown":
        return f"Allowed only under conditions ({refs}); the product information is not enough to confirm they are met."
    return f"Allowed under conditions ({refs}); the conditions checked are met."


def baseline_finding(ingredient: Ingredient, product: Product, rows: list[AnnexRow]) -> RegulatoryFinding:
    status = status_from_rows(rows)
    conditions = [c for r in rows for c in baseline_conditions(r, product)]
    compliance = compliance_from(status, conditions)
    return RegulatoryFinding(
        position=ingredient.position,
        ingredient=ingredient.normalized,
        matched=ingredient.matched,
        regulatory_status=status,
        entries=entries_from_rows(rows),
        conditions=conditions,
        compliance_check=compliance,
        explanation=baseline_explanation(status, rows, compliance),
        missing_information=missing_from(conditions, product),
        evidence_confidence="high",
        sources=sorted({r.source_id for r in rows}),
    )


# ---- invariants --------------------------------------------------------------------
def apply_ocr_confidence(finding: RegulatoryFinding, ingredient: Ingredient) -> RegulatoryFinding:
    if ingredient.confidence < OCR_CONFIDENCE_THRESHOLD:
        finding.evidence_confidence = "low"
        if OCR_NOTE not in finding.missing_information:
            finding.missing_information.append(OCR_NOTE)
    return finding
