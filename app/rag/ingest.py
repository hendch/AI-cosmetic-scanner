import csv
import json
import re
from collections import Counter

import yaml
import pymupdf

from . import config
from .chunkers import record_to_text

REQUIRED = ("ingredient", "source_id", "section", "status")


def load_sources() -> dict:
    return yaml.safe_load(config.SOURCES_YAML.read_text(encoding="utf-8"))["sources"]


def load_structured() -> list[dict]:
    records = []
    for p in sorted(config.CORPUS_STRUCTURED.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        records += data if isinstance(data, list) else [data]
    for r in records:
        missing = [k for k in REQUIRED if not r.get(k)]
        if missing:
            raise ValueError(f"Record {r.get('ingredient')} missing {missing}")
    return records


def _read_raw(path) -> str:
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    return path.read_text(encoding="utf-8")


def _registry_rows() -> list[dict]:
    with config.SOURCES_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# Section headings of SCCS opinions, alone on their line ("3. OPINION", "4 \nCONCLUSION"). The table of
# contents (dots and page numbers) does not match. Opening sections need their number, so the cover
# page ("OPINION" / "on Phenoxyethanol") does not match; closing ones may lose it with the page numbers.
_HEADING = re.compile(r"^[ \t]*(?:\d{1,2}\.?[ \t]*\n?[ \t]*(ABSTRACT|BACKGROUND|TERMS OF REFERENCE|"
                      r"MANDATE FROM THE EUROPEAN COMMISSION|OPINION|SCIENTIFIC ADVICE)|"
                      r"(?:\d{1,2}\.?[ \t]*\n?[ \t]*)?(CONCLUSION|MINORITY OPINION|(?:ADDITIONAL )?REFERENCES|"
                      r"GLOSSARY OF TERMS|LIST OF ABBREVIATIONS|ANNEX))"
                      r"(?: SUBMISSION [IVX]+[^\n]*)?[ \t]*$", re.M)
SCCS_SECTIONS = {"ABSTRACT": "Abstract", "OPINION": "Opinion", "SCIENTIFIC ADVICE": "Opinion",
                 "CONCLUSION": "Conclusion", "MINORITY OPINION": "Minority opinion"}
_STOP = {"REFERENCES", "ADDITIONAL REFERENCES", "GLOSSARY OF TERMS", "LIST OF ABBREVIATIONS", "ANNEX"}


def _pdf_body(path) -> str:
    """PDF text without the running header/footer lines repeated on most pages."""
    with pymupdf.open(path) as doc:
        pages = [page.get_text().splitlines() for page in doc]
    counts = Counter(line.strip() for lines in pages for line in set(lines) if line.strip())
    repeated = {line for line, n in counts.items() if n > len(pages) * 0.3}
    keep = [line for lines in pages for line in lines
            if line.strip() not in repeated and not re.fullmatch(r"\s*(\d{1,3}|_{5,})\s*", line)]
    return "\n".join(keep)


def sccs_sections(text: str) -> list[tuple[str, str]]:
    """(section, text) for the parts worth retrieving: abstract, opinion, conclusion, minority opinion."""
    marks = [(m.start(), m.end(), m.group(1) or m.group(2)) for m in _HEADING.finditer(text)]
    out = []
    for i, (_, end, head) in enumerate(marks):
        if head in _STOP and any(h == "CONCLUSION" for _, _, h in marks[:i]):
            break
        name = SCCS_SECTIONS.get(head)
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text[end:nxt])).strip()
        if name and len(body) > 200:
            out.append((name, body))
    return out


def load_sccs_opinions() -> list[dict]:
    """SCCS opinions registered in corpus/sources.csv, with the source_id the report checks against."""
    docs = []
    for r in _registry_rows():
        path = config.ROOT / "corpus" / r["filename"]
        if r["doc_type"] != "sccs_opinion" or not path.exists():
            continue
        docs.append({"source_id": r["source_id"], "title": r["document_title"], "url": r["url"] or None,
                     "date": r["publication_date"] or None,
                     "ingredients": [i.strip() for i in r["ingredients"].split(";") if i.strip()],
                     "sections": sccs_sections(_pdf_body(path))})
    return docs


def load_clp_rows() -> tuple[dict, list[dict]]:
    """(registry entry, rows) of the CLP summary table."""
    source = next(r for r in _registry_rows() if r["source_id"] == "clp_test_ingredients")
    with config.CLP_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {"source_id": source["source_id"], "title": source["document_title"],
            "url": source["url"] or None, "date": source["publication_date"] or None}, rows


def load_documents(records: list[dict], sources: dict) -> list[dict]:
    """Documents for the fixed-size baseline. Uses the raw file when present in
    corpus/raw/, otherwise renders the structured records as flat text."""
    docs = []
    for sid, src in sources.items():
        raw = config.CORPUS_RAW / src["file"] if src.get("file") else None
        if raw and raw.exists():
            docs.append({"source_id": sid, "text": _read_raw(raw), "origin": raw.name})
        else:
            recs = [r for r in records if r["source_id"] == sid]
            if recs:
                text = "\n\n".join(record_to_text(r, sources) for r in recs)
                docs.append({"source_id": sid, "text": text, "origin": "flattened records"})
    return docs