import hashlib
from dataclasses import dataclass, field

from . import config


@dataclass
class Chunk:
    evidence_id: str
    text: str
    payload: dict = field(default_factory=dict)


def norm(s: str) -> str:
    return " ".join(s.lower().split())


# Strategy A: fixed-size chunks (token windows) for long text
def fixed(text: str, tokenizer, size: int = config.FIXED_CHUNK_TOKENS,
          overlap: int = config.FIXED_CHUNK_OVERLAP) -> list[str]:
    """Token windows measured with the embedding model's own tokenizer,
    so a 500-token chunk really fits the model's 512 limit."""
    # Tokenize the whole text without the length warning, then restore the limit: the same tokenizer
    # embeds the chunks afterwards and must keep truncating at the model's 512 tokens.
    limit, tokenizer.model_max_length = tokenizer.model_max_length, 10**9
    try:
        enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    finally:
        tokenizer.model_max_length = limit
    offs = enc["offset_mapping"]
    step = size - overlap
    chunks = []
    for start in range(0, len(offs), step):
        window = offs[start:start + size]
        if not window:
            break
        chunks.append(text[window[0][0]:window[-1][1]])
        if start + size >= len(offs):
            break
    return chunks


# Strategy B: structured chunks for regulatory records, with metadata
_FIELDS = [("status", "Status"), ("restriction", "Restriction"),
           ("max_concentration", "Maximum concentration"),
           ("product_type", "Product type"), ("conditions", "Conditions"),
           ("warnings", "Warnings"),
           ("hazard", "Hazard classification"),
           ("opinion", "Scientific opinion"),
           ("source_quote", "Source wording")]


def record_to_text(rec: dict, sources: dict) -> str:
    src = sources.get(rec["source_id"], {})
    head = f"Ingredient: {rec['ingredient']}"
    if rec.get("aliases"):
        head += f" (also known as: {', '.join(rec['aliases'])})"
    where = f"Source: {src.get('title', rec['source_id'])}, {rec['section']}"
    if rec.get("entry_ref"):
        where += f", entry {rec['entry_ref']}"
    lines = [head, where]
    lines += [f"{label}: {rec[k]}" for k, label in _FIELDS if rec.get(k)]
    return "\n".join(lines)


def record_id(rec: dict) -> str:
    if rec.get("id"):
        return rec["id"]
    key = f"{rec['source_id']}|{rec['ingredient']}|{rec['section']}|{rec.get('entry_ref', '')}"
    return "EV-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()


def structured(rec: dict, sources: dict) -> Chunk:
    src = sources.get(rec["source_id"], {})
    names = sorted({norm(rec["ingredient"]), *[norm(a) for a in rec.get("aliases", [])]})
    text = record_to_text(rec, sources)
    eid = record_id(rec)
    return Chunk(eid, text, {
        "evidence_id": eid, "text": text, "strategy": "structured",
        "ingredient": norm(rec["ingredient"]), "names": names,
        "source_id": rec["source_id"], "source": src.get("title", rec["source_id"]),
        "section": rec["section"], "entry_ref": rec.get("entry_ref"),
        "status": rec.get("status"), "product_type": rec.get("product_type"),
        "max_concentration": rec.get("max_concentration"),
        "source_date": src.get("date"), "url": src.get("url"),
    })

# Strategy B also covers the regulatory annexes: one chunk per annex entry (corpus/regulatory/*.csv),
# with the legal fields as metadata, so the regulatory agent can retrieve exact entries.
REGULATION_FIELDS = ("product_type_body_parts", "max_concentration", "other_conditions", "warnings",
                     "inci_names", "chemical_name", "cas", "status", "consolidated_version", "source_url")


def sccs_chunks(doc: dict, tokenizer, size: int = config.SCCS_CHUNK_TOKENS,
                overlap: int = config.SCCS_CHUNK_OVERLAP) -> list[Chunk]:
    """An SCCS opinion (ingest.load_sccs_opinions) -> token windows inside each section,
    each tagged with the section and the opinion's ingredients (for the ingredient filter)."""
    names = sorted({norm(i) for i in doc["ingredients"]})
    chunks = []
    for section, text in doc["sections"]:
        slug = section.lower().replace(" ", "_")
        for n, window in enumerate(fixed(text, tokenizer, size, overlap)):
            eid = f"{doc['source_id']}#{slug}-{n:03d}"
            body = f"{doc['title']} - {section}\n{window.strip()}"
            chunks.append(Chunk(eid, body, {
                "evidence_id": eid, "text": body, "strategy": "structured", "doc_type": "sccs_opinion",
                "ingredient": names[0] if names else "", "names": names, "ingredients": ";".join(names),
                "source_id": doc["source_id"], "source": doc["title"], "section": section,
                "source_date": doc.get("date"), "url": doc.get("url"),
            }))
    return chunks


CLP_FIELDS = ("cas", "echa_substance_name", "harmonised", "annex_vi_index_no", "atp", "hazard_classes",
              "hazard_statements", "notified_classification", "note")


def clp_text(r: dict) -> str:
    """Same wording as app/report/sources.clp_text, so the report excerpt and the passage agree."""
    head = f"{r['echa_substance_name']} (CAS {r['cas']})"
    if r["harmonised"].strip().lower() == "yes":
        text = (f"{head}: harmonised classification, CLP Annex VI index {r['annex_vi_index_no']} ({r['atp']}): "
                f"{r['hazard_classes']}. Hazard statements: {r['hazard_statements']}.")
    elif r["notified_classification"]:
        text = f"{head}: no harmonised classification; notified classification: {r['notified_classification']}."
    else:
        text = f"{head}: no harmonised classification in Annex VI to CLP."
    return text + (f" Note: {r['note']}" if r.get("note") else "")


def clp_row(r: dict, source: dict) -> Chunk:
    """One row of corpus/toxicology/clp/clp_test_ingredients.csv -> one chunk."""
    name = norm(r["ingredient"])
    eid = f"{source['source_id']}#{name}"
    text = f"Ingredient: {r['ingredient']}\nCLP classification (ECHA): {clp_text(r)}"
    return Chunk(eid, text, {
        "evidence_id": eid, "text": text, "strategy": "structured", "doc_type": "clp",
        "ingredient": name, "names": sorted({name, norm(r["echa_substance_name"])}), "ingredients": name,
        "source_id": source["source_id"], "source": source["title"], "section": "CLP classification",
        "source_date": source.get("date"), "url": r.get("notified_source_url") or source.get("url"),
        **{k: r.get(k, "") for k in CLP_FIELDS},
    })


def annex_row(row) -> Chunk:
    """`row` is an app.regulatory.kb.AnnexRow."""
    names = sorted({norm(i) for i in row.ingredients}
                   | {norm(n) for n in row.inci_names.split(";") if n.strip()})
    eid = f"{row.source_id}#{row.entry}"
    text = row.as_text()
    return Chunk(eid, text, {
        "evidence_id": eid, "text": text, "strategy": "structured", "doc_type": "regulation",
        "ingredient": norm(row.ingredients[0]) if row.ingredients else "", "names": names,
        "ingredients": ";".join(row.ingredients), "annex": row.annex, "entry": row.entry,
        "source_id": row.source_id, "source": f"Regulation (EC) No 1223/2009, Annex {row.annex}",
        "section": f"Annex {row.annex}", "entry_ref": row.entry,
        "source_date": row.consolidated_version, "url": row.source_url,
        **{k: getattr(row, k) for k in REGULATION_FIELDS},
    })
