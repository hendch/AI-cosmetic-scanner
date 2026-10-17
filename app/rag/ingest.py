import json
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