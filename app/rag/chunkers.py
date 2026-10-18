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
    tokenizer.model_max_length = 10**9            
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
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
