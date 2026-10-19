"""The only place the toxicology agent asks for evidence.

Two kinds of passages, both in the shared RAG index (app/rag, built by `python -m app.rag.index`):
- "clp": one passage per substance of corpus/toxicology/clp/clp_test_ingredients.csv (ECHA classification).
- "sccs_opinion": sections of the SCCS opinions in corpus/toxicology/sccs/ (abstract, opinion, conclusion).

RETRIEVAL_BACKEND selects the implementation (all return the same Passage objects):
- "rag": the RAG index in the same process (embeddings through the HF router). Used on Render.
- "http": the same RAG endpoint over HTTP: POST {RETRIEVAL_URL}/rag/retrieve.
- "local" (default): the same passages read from the shipped index file, ranked by word overlap
  instead of embeddings (tests, offline work: no API call).
"""

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from app.rag import config as rag_config

CLP, SCCS = "clp", "sccs_opinion"
CLP_QUERY = "CLP hazard classification and hazard statements"
SCCS_QUERY = ("SCCS conclusion on the use in cosmetic products: hazards, skin sensitisation, toxicity, "
              "maximum concentration considered acceptable")
SECTION_BONUS = {"Conclusion": 2, "Abstract": 1}  # local ranking: the SCCS answers first


@dataclass
class Passage:
    evidence_id: str
    source_id: str
    doc_type: str  # clp | sccs_opinion
    section: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class RetrievalError(RuntimeError):
    pass


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


@lru_cache(maxsize=1)
def _shipped() -> tuple[dict, ...]:
    """Toxicology passages (payloads only) of the index shipped in corpus/index/."""
    path = rag_config.INDEX_EXPORT_DIR / f"{rag_config.COLLECTIONS['structured']}.jsonl"
    if not path.exists():
        return ()
    payloads = (json.loads(line)["payload"] for line in path.read_text(encoding="utf-8").splitlines() if line)
    return tuple(p for p in payloads if p.get("doc_type") in (CLP, SCCS))


def covered(ingredient: str) -> bool:
    """False when the corpus has no toxicology passage for this name: no need to call the embedding API."""
    name = _norm(ingredient)
    return not _shipped() or any(name in p.get("names", []) for p in _shipped())


def _local_search(ingredient: str, query: str, top_k: int, doc_type: str) -> list[Passage]:
    name, words = _norm(ingredient), set(re.findall(r"[a-z]{4,}", query.lower()))
    hits = [p for p in _shipped() if p["doc_type"] == doc_type and name in p.get("names", [])]

    def score(p: dict) -> int:
        text = p["text"].lower()
        return sum(w in text for w in words) + SECTION_BONUS.get(p.get("section", ""), 0)

    ranked = sorted(hits, key=lambda p: (-score(p), p["evidence_id"]))[:top_k]
    return [Passage(p["evidence_id"], p["source_id"], p["doc_type"], p.get("section") or "", p["text"],
                    float(score(p)), p) for p in ranked]


def _from_items(items: list[dict]) -> list[Passage]:
    out = []
    for x in items:
        meta = x.get("metadata") or {}
        if meta.get("doc_type") in (CLP, SCCS):
            out.append(Passage(x["evidence_id"], meta.get("source_id", ""), meta["doc_type"], x.get("section") or "",
                               x.get("text", ""), float(x.get("score", 0.0)), meta))
    return out


def _rag_search(ingredient: str, query: str, top_k: int, doc_type: str) -> list[Passage]:
    from app.common.llm import LLMError
    from app.rag.retrieve import IndexNotBuilt, retrieve
    from app.rag.schemas import RetrieveRequest

    try:
        res = retrieve(RetrieveRequest(ingredient=ingredient, query=query, top_k=top_k, strategy="structured",
                                       doc_types=[doc_type]))
    except (IndexNotBuilt, LLMError, RuntimeError) as e:  # RuntimeError: local Qdrant folder locked
        raise RetrievalError(f"RAG retrieval failed: {e}") from e
    return _from_items([r.model_dump() for r in res.results])


def _http_search(ingredient: str, query: str, top_k: int, doc_type: str) -> list[Passage]:
    url = os.environ.get("RETRIEVAL_URL", "").rstrip("/")
    if not url:
        raise RetrievalError("RETRIEVAL_BACKEND=http but RETRIEVAL_URL is not set")
    body = {"ingredient": ingredient, "query": query, "top_k": top_k, "strategy": "structured", "doc_types": [doc_type]}
    try:
        r = httpx.post(f"{url}/rag/retrieve", json=body, headers={"X-API-Key": os.environ.get("SCANNER_API_KEY", "")},
                       timeout=30)
        r.raise_for_status()
        return _from_items(r.json().get("results", []))
    except (httpx.HTTPError, ValueError) as e:
        raise RetrievalError(f"retrieval service failed: {e}") from e


def search_toxicology(ingredient: str, top_k: int = 4) -> list[Passage]:
    """The CLP passage (if any) first, then up to top_k SCCS passages. Empty list = nothing in the corpus."""
    if not covered(ingredient):
        return []
    backend = os.environ.get("RETRIEVAL_BACKEND", "local")
    search = {"rag": _rag_search, "http": _http_search}.get(backend, _local_search)
    return search(ingredient, CLP_QUERY, 1, CLP) + search(ingredient, SCCS_QUERY, top_k, SCCS)
