"""Deterministic part of the toxicology agent (no LLM).

- Hazards come from the retrieved CLP passage: each human-health hazard statement (H3xx) becomes a
  Hazard, with the passage text as its quote. Environmental statements (H4xx) are not consumer health.
- concern_level is decided here, never by the LLM:
    high      harmonised carcinogen / mutagen / reproductive toxicant, category 1A or 1B
    moderate  any other CMR classification (category 2, or notified only), sensitiser, STOT RE
    low       other human-health hazards (irritation, eye damage, acute toxicity, ...)
    none_identified  CLP data found, no human-health classification
    insufficient_evidence  no CLP passage
  SCCS findings accepted from the LLM can raise it to moderate, when the quote states a concern ("not safe",
  "does not support the safe use", ...) or the endpoint is sensitisation or CMR. Otherwise (a "no concern"
  conclusion) they leave it unchanged. The concern is read from the quoted SCCS words, not from the LLM's label.
- The rule result is also the fallback when the LLM is not called, fails, or answers badly.
"""

import re

from app.common_schemas import Ingredient
from app.toxicology.retrieval import CLP, SCCS, Passage
from app.toxicology.schemas import Hazard, IngredientFinding

OCR_CONFIDENCE_THRESHOLD = 0.8
LEVELS = ["none_identified", "low", "moderate", "high"]
CMR = {"carcinogenicity", "mutagenicity", "reproductive_toxicity"}
ENDPOINTS = [(r"^H34[01]", "mutagenicity"), (r"^H35[01]", "carcinogenicity"), (r"^H36[0-2]", "reproductive_toxicity"),
             (r"^H3(17|34)", "sensitisation"), (r"^H31[45]", "skin_irritation"), (r"^H31[89]", "eye_irritation")]
RISK_NOTE = ("A hazard classification describes the pure substance; the risk for a consumer depends on its "
             "concentration in the product and on exposure, which the label does not give.")


def endpoint(code: str) -> str:
    return next((name for pattern, name in ENDPOINTS if re.match(pattern, code)), "other")


def clp_classifications(p: Passage) -> list[tuple[str, str, bool]]:
    """(hazard class, H-code, harmonised) for each human-health classification in a CLP passage."""
    m = p.metadata
    harmonised = str(m.get("harmonised", "")).strip().lower() == "yes"
    if harmonised:
        classes = [c.strip() for c in str(m.get("hazard_classes", "")).split(";") if c.strip()]
        codes = [c.strip() for c in str(m.get("hazard_statements", "")).split(";") if c.strip()]
        pairs = list(zip(classes, codes)) if len(classes) == len(codes) else [("", c) for c in codes]
    else:
        pairs = re.findall(r"([^;()]+?)\s*\((H\d{3}[A-Za-z]{0,2})\)", str(m.get("notified_classification", "")))
    seen, out = set(), []
    for cls, code in pairs:
        cls, code = cls.strip(), code.strip()
        if code.startswith("H3") and (cls, code) not in seen:
            seen.add((cls, code))
            out.append((cls, code, harmonised))
    return out


def clp_level(cls: str, code: str, harmonised: bool) -> str:
    ep = endpoint(code)
    if ep in CMR and harmonised and re.search(r"\b1[AB]?\b", cls):
        return "high"
    if ep in CMR or ep == "sensitisation" or cls.startswith("STOT RE"):
        return "moderate"
    return "low"


# SCCS wording for "this use raised a concern" (BP-3: "is not safe for the consumer"; MI: "does not support
# the safe use"; parabens 2013: "has not been provided for the safe use").
# "not applicable to sprayable products" is a scope limit, not a concern.
SCCS_CONCERN = re.compile(r"\bnot\s+(?:be\s+)?(?:considered\s+)?safe\b|\bcannot\s+be\s+(?:considered\s+)?safe\b|"
                          r"\bunsafe\b|\bnot\s+(?:\w+\s+){0,3}(?:for\s+)?(?:the\s+)?safe(?:ty\s+of|\s+use)", re.I)


def sccs_concern(quote: str) -> bool:
    return bool(SCCS_CONCERN.search(" ".join(quote.split())))


def sccs_level(ep: str, quote: str = "") -> str:
    """none_identified = no raise: a "no concern up to 1 %" conclusion is not a hazard."""
    return "moderate" if ep in CMR or ep == "sensitisation" or sccs_concern(quote) else "none_identified"


def highest(levels: list[str]) -> str:
    return max(levels, key=LEVELS.index) if levels else "none_identified"


def apply_ocr_confidence(finding: IngredientFinding, ingredient: Ingredient) -> IngredientFinding:
    if ingredient.confidence < OCR_CONFIDENCE_THRESHOLD:
        finding.evidence_confidence = "low"
        if "ingredient name from OCR, unverified" not in finding.missing_information:
            finding.missing_information.append("ingredient name from OCR, unverified")
    return finding


def not_assessed(ingredient: Ingredient, reason: str, missing: str) -> IngredientFinding:
    return IngredientFinding(position=ingredient.position, ingredient=ingredient.normalized, matched=ingredient.matched,
                             concern_level="insufficient_evidence", risk_interpretation=reason,
                             missing_information=[missing], evidence_confidence="low")


def baseline_finding(ingredient: Ingredient, passages: list[Passage]) -> IngredientFinding:
    """Rule result from the retrieved passages (at least one)."""
    clp = next((p for p in passages if p.doc_type == CLP), None)
    sccs = [p for p in passages if p.doc_type == SCCS]
    titles = sorted({p.metadata.get("source") or p.source_id for p in sccs})
    found = clp_classifications(clp) if clp else []
    hazards = [Hazard(endpoint=endpoint(code), classification=f"CLP {cls} ({code})" + ("" if harm else ", notified"),
                      source_id=clp.source_id, quote=clp.text) for cls, code, harm in found]
    missing = ["concentration"]

    if clp is None:
        level, confidence = "insufficient_evidence", "low"
        text = "No CLP classification for this substance in the corpus."
        missing.insert(0, "CLP classification")
    elif found:
        level = highest([clp_level(*f) for f in found])
        harmonised = all(f[2] for f in found)
        confidence = "high" if harmonised else "medium"
        kind = "harmonised EU classification" if harmonised else "classification notified by companies, not harmonised"
        text = f"CLP {kind}: {', '.join(h.classification.removeprefix('CLP ') for h in hazards)}. {RISK_NOTE}"
    else:
        level, confidence = "none_identified", "medium"
        text = "No human-health hazard classification for this substance in the CLP data."
    if sccs:
        text += f" The SCCS assessed its use in cosmetic products ({'; '.join(titles)})."
        confidence = "medium" if confidence == "low" else confidence

    return IngredientFinding(
        position=ingredient.position, ingredient=ingredient.normalized, matched=ingredient.matched,
        hazards=hazards, concern_level=level, risk_interpretation=text, missing_information=missing,
        evidence_confidence=confidence, sources=list(dict.fromkeys(p.source_id for p in passages)),
    )
