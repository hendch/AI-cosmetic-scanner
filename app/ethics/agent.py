"""Cruelty-free agent: a deterministic lookup, no LLM and no RAG.

1. The brand (each part of an Open Beauty Facts "Brand A, Brand B" field) is looked up in PETA's
   Beauty Without Bunnies lists (data/peta_brands.json, built by scripts/build_peta_brands.py).
2. Its parent company comes from PETA's own "Brand (Parent)" names, else from
   corpus/ethics/brand_parents.csv. The parent is looked up only when the brand itself is not listed:
   PETA lists brands of the same group separately (Urban Decay doesn't test, L'Oreal does).
3. Open Beauty Facts cruelty-free labels are a brand claim, never a verification.

Status rules:
- VERIFIED: brand on PETA's "don't test" list (high confidence), or its parent is (medium).
- CONFLICTING: the product is labelled cruelty-free, but the brand or its parent is on the "do test" list.
- CLAIMED: cruelty-free label, no listing found.
- NOT_VERIFIED: no claim and no "don't test" listing, a "do test" listing, or unknown brand.
The EU animal-testing ban is always added as context but never raises the status.
"""

import csv
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.common_schemas import ProductInput
from app.ethics.schemas import Certification, EthicsEvidence, EthicsResponse

ROOT = Path(__file__).resolve().parents[2]
PETA_JSON = ROOT / "data" / "peta_brands.json"  # gitignored; override with PETA_BRANDS_PATH
PARENTS_CSV = ROOT / "corpus" / "ethics" / "brand_parents.csv"

RULES_VERSION = "rules-v1"
PETA = "PETA Beauty Without Bunnies"
PETA_ID = "peta_beauty_without_bunnies"
DONT_TEST, DO_TEST = "dont_test", "do_test"

# Open Beauty Facts labels_tags treated as brand claims (user-contributed, not verification).
CRUELTY_FREE_LABELS = {
    "en:cruelty-free",
    "en:not-tested-on-animals",
    "en:leaping-bunny",
    "en:peta-cruelty-free",
}

EU_BAN_EVIDENCE = EthicsEvidence(
    type="regulatory",
    source="Regulation (EC) No 1223/2009, Art. 18",
    detail="Animal testing of cosmetics and their ingredients is banned for products marketed in the EU.",
    source_id="eu_1223_2009_art18",
)

LEGAL_FORMS = {"inc", "ltd", "llc", "gmbh", "ag", "sa", "se", "co", "corp", "corporation", "kg", "plc", "bv", "srl", "spa"}
PARENT_IN_NAME = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")  # "Urban Decay (L'Oréal)"


def normalize(name: str) -> str:
    """Same rule as scripts/build_peta_brands.py, minus legal forms: "L’Oréal Paris GmbH" -> "loreal paris"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9 ]", "", ascii_name.lower()).split()
    while len(words) > 1 and words[-1] in LEGAL_FORMS:
        words.pop()
    return " ".join(words)


@dataclass(frozen=True)
class Listing:
    name: str
    status: str  # dont_test | do_test
    url: str


@dataclass
class BrandList:
    retrieved: str
    by_name: dict[str, list[Listing]] = field(default_factory=dict)
    parent_of: dict[str, str] = field(default_factory=dict)  # from "Brand (Parent)" names

    def find(self, name: str) -> Listing | None:
        hits = self.by_name.get(normalize(name), [])
        # A name listed as both (rare duplicates) is reported as testing: never verify on a doubt.
        return next((h for h in hits if h.status == DO_TEST), hits[0] if hits else None)


def parse_peta(data: dict) -> BrandList:
    brands = BrandList(retrieved=data.get("retrieved", ""))
    for c in data["companies"]:
        listing = Listing(c["name"], c["status"], c.get("url", ""))
        m = PARENT_IN_NAME.match(c["name"])
        for key in {normalize(c["name"]), normalize(m.group(1)) if m else ""} - {""}:
            brands.by_name.setdefault(key, []).append(listing)
        if m:
            brands.parent_of[normalize(m.group(1))] = m.group(2).strip()
    return brands


@lru_cache(maxsize=4)
def _load_peta(path: str) -> BrandList | None:
    p = Path(path)
    return parse_peta(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else None


def load_peta() -> BrandList | None:
    return _load_peta(os.environ.get("PETA_BRANDS_PATH") or str(PETA_JSON))


@lru_cache(maxsize=1)
def load_parents() -> dict[str, str]:
    with PARENTS_CSV.open(encoding="utf-8", newline="") as f:
        return {normalize(r["brand"]): r["parent_company"].strip() for r in csv.DictReader(f)}


def _brand_names(brand: str) -> list[str]:
    return list(dict.fromkeys(p.strip() for p in re.split(r"[,;]", brand) if p.strip()))


def _listing_evidence(listing: Listing, who: str, retrieved: str) -> EthicsEvidence:
    if listing.status == DONT_TEST:
        return EthicsEvidence(type="certification", source=PETA, source_id=PETA_ID,
                              detail=f"{who} '{listing.name}' is on PETA's list of companies that don't test on "
                                     f"animals (retrieved {retrieved}).")
    return EthicsEvidence(type="third_party_report", source=PETA, source_id=PETA_ID,
                          detail=f"{who} '{listing.name}' is on PETA's list of companies that test on animals "
                                 f"(retrieved {retrieved}).")


def analyze(payload: ProductInput, peta: BrandList | None = None, parents: dict[str, str] | None = None) -> EthicsResponse:
    peta = peta if peta is not None else load_peta()
    parents = parents if parents is not None else load_parents()
    brand = payload.product.brand.strip()
    claims = sorted(CRUELTY_FREE_LABELS.intersection(payload.product.labels))
    warnings = list(payload.warnings)
    if peta is None:
        warnings.append("PETA brand list not available (data/peta_brands.json): run python -m scripts.build_peta_brands. "
                        "No certification list was checked.")
    common = dict(prompt_version=RULES_VERSION, brand=brand, certifications_checked=[PETA] if peta else [],
                  warnings=warnings)

    if not brand:
        return EthicsResponse(
            **common,
            status="NOT_VERIFIED",
            status_reason="Brand unknown, so no claim or certification could be checked.",
            evidence=[EU_BAN_EVIDENCE],
            missing_information=["brand"],
            evidence_confidence="low",
        )

    names = _brand_names(brand)
    own = next((hit for n in names if peta and (hit := peta.find(n))), None)
    parent = next((p for n in names if (p := (peta.parent_of.get(normalize(n)) if peta else None)
                                        or parents.get(normalize(n)))), None)
    parent_listing = peta.find(parent) if (peta and parent) else None

    claim_evidence = [EthicsEvidence(type="brand_claim", source="Open Beauty Facts labels",
                                     detail=", ".join(claims), source_id="obf_labels")] if claims else []
    retrieved = peta.retrieved if peta else ""
    common["parent_company"] = parent

    # The brand's own listing decides; the parent only adds context (or decides when the brand is not listed).
    deciding, who = (own, "Brand") if own else (parent_listing, "Parent company") if parent_listing else (None, "")
    listing_evidence = [_listing_evidence(deciding, who, retrieved)] if deciding else []
    if own and parent_listing and parent_listing.status != own.status:
        listing_evidence.append(_listing_evidence(parent_listing, "Parent company", retrieved))
    evidence = listing_evidence + claim_evidence + [EU_BAN_EVIDENCE]
    via_parent = f"{brand} is not listed by PETA; its parent company {parent}" if not own else f"{brand}"

    if deciding and deciding.status == DONT_TEST:
        reason = f"{via_parent} is on PETA's list of companies that don't test on animals."
        if own and parent_listing and parent_listing.status == DO_TEST:
            reason += f" Its parent company {parent} is on PETA's list of companies that test on animals."
        return EthicsResponse(
            **common,
            status="VERIFIED",
            status_reason=reason,
            evidence=evidence,
            certifications_found=[Certification(name=PETA, source_id=PETA_ID)],
            missing_information=[] if own else ["brand-level certification"],
            evidence_confidence="high" if own else "medium",
        )

    if deciding:  # do_test
        tests = f"{via_parent} is on PETA's list of companies that test on animals."
        if claims:
            return EthicsResponse(
                **common,
                status="CONFLICTING",
                status_reason=f"The product is labelled cruelty-free on Open Beauty Facts, but {tests}",
                evidence=evidence,
                conflicts=[f"Open Beauty Facts labels ({', '.join(claims)}) vs PETA listing '{deciding.name}' (tests on animals)"],
                evidence_confidence="medium",
            )
        return EthicsResponse(
            **common,
            status="NOT_VERIFIED",
            status_reason=tests,
            evidence=evidence,
            evidence_confidence="high" if own else "medium",
        )

    if not peta:
        not_found = f"no certification list was available to check {brand}"
    elif parent:
        not_found = f"neither {brand} nor its parent company {parent} is on PETA's lists"
    else:
        not_found = f"{brand} is not on PETA's lists"
    if claims:
        return EthicsResponse(
            **common,
            status="CLAIMED",
            status_reason=f"The product carries a cruelty-free label on Open Beauty Facts, but {not_found}.",
            evidence=evidence,
            missing_information=["independent certification"],
            evidence_confidence="medium",
        )
    return EthicsResponse(
        **common,
        status="NOT_VERIFIED",
        status_reason=f"No cruelty-free claim on the product, and {not_found}.",
        evidence=evidence,
        missing_information=["brand claim", "independent certification"],
        evidence_confidence="medium" if peta else "low",
    )
