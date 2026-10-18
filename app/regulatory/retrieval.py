"""The only place the regulatory agent asks for evidence.

RETRIEVAL_BACKEND selects the implementation (all return the same Passage objects):
- "rag": the RAG vector index (app/rag, Qdrant + bge-small) in the same process. Annex entries are
  indexed as structure-aware chunks (one chunk per entry, legal fields as metadata). Used on Render.
- "http": the same RAG endpoint over HTTP: POST {RETRIEVAL_URL}/rag/retrieve (header X-API-Key from
  SCANNER_API_KEY), for a separately deployed retrieval service.
- "local" (default): reads corpus/regulatory/ directly, no embeddings (tests, offline work).
"""

import os
from dataclasses import dataclass, field

import httpx

from app.regulatory.kb import AnnexRow, load_kb

CONDITION_FIELDS = [
    "product_type_body_parts", "max_concentration", "other_conditions", "warnings",
    "inci_names", "chemical_name", "cas", "status", "consolidated_version", "source_url",
]


@dataclass
class Passage:
    chunk_id: str
    source_id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)

    @property
    def annex(self) -> str | None:
        return self.metadata.get("annex")

    @property
    def entry(self) -> str | None:
        return self.metadata.get("entry")

    def to_row(self) -> AnnexRow:
        """Rebuild an annex row from the chunk metadata (missing fields stay empty)."""
        m = self.metadata
        ingredients = m.get("ingredients") or m.get("ingredient") or ""
        if isinstance(ingredients, str):
            ingredients = [i.strip() for i in ingredients.split(";") if i.strip()]
        return AnnexRow(
            source_id=self.source_id,
            annex=str(m.get("annex", "")),
            entry=str(m.get("entry", "")),
            status=m.get("status", "prohibited" if m.get("annex") == "II" else "restricted"),
            ingredients=tuple(ingredients),
            **{k: str(m.get(k, "") or "") for k in CONDITION_FIELDS if k != "status"},
        )


class RetrievalError(RuntimeError):
    pass


def _local_search(ingredient: str, top_k: int) -> list[Passage]:
    kb = load_kb()
    canonical = kb.canonical(ingredient) or ingredient.strip().lower()
    passages = []
    for row in kb.entries_for(canonical)[:top_k]:
        meta = {"doc_type": "regulation", "ingredient": canonical, "ingredients": ";".join(row.ingredients),
                "annex": row.annex, "entry": row.entry,
                **{k: getattr(row, k) for k in CONDITION_FIELDS}}
        passages.append(Passage(chunk_id=f"{row.source_id}#{row.entry}", source_id=row.source_id,
                                text=row.as_text(), score=1.0, metadata=meta))
    return passages


def _from_rag(items: list[dict]) -> list[Passage]:
    """RAG results -> passages. Only annex-entry chunks (with annex/entry metadata) are kept."""
    out = []
    for x in items:
        meta = x.get("metadata") or {}
        if meta.get("doc_type") != "regulation" or not meta.get("annex"):
            continue
        out.append(Passage(chunk_id=x["evidence_id"], source_id=meta.get("source_id", ""), text=x.get("text", ""),
                           score=float(x.get("score", 0.0)), metadata=meta))
    return out


def _rag_search(query: str, ingredient: str, top_k: int) -> list[Passage]:
    from app.common.llm import LLMError
    from app.rag.retrieve import IndexNotBuilt, retrieve
    from app.rag.schemas import RetrieveRequest

    try:
        res = retrieve(RetrieveRequest(ingredient=ingredient, query=query, top_k=top_k, strategy="structured"))
    except (IndexNotBuilt, LLMError) as e:
        raise RetrievalError(f"RAG retrieval failed: {e}") from e
    return _from_rag([r.model_dump() for r in res.results])


def _http_search(query: str, ingredient: str, top_k: int) -> list[Passage]:
    url = os.environ.get("RETRIEVAL_URL", "").rstrip("/")
    if not url:
        raise RetrievalError("RETRIEVAL_BACKEND=http but RETRIEVAL_URL is not set")
    body = {"ingredient": ingredient, "query": query, "top_k": top_k, "strategy": "structured"}
    headers = {"X-API-Key": os.environ.get("SCANNER_API_KEY", "")}
    try:
        r = httpx.post(f"{url}/rag/retrieve", json=body, headers=headers, timeout=30)
        r.raise_for_status()
        results = r.json().get("results", [])
    except (httpx.HTTPError, ValueError) as e:
        raise RetrievalError(f"retrieval service failed: {e}") from e
    return _from_rag(results)


def search_regulation(ingredient: str, product_type: str | None = None, top_k: int = 5) -> list[Passage]:
    """Regulation passages about one ingredient. Empty list = nothing found."""
    query = f"{ingredient} restrictions conditions of use" + (f" {product_type.replace('_', '-')}" if product_type else "")
    backend = os.environ.get("RETRIEVAL_BACKEND", "local")
    search = {"http": _http_search, "rag": _rag_search}.get(backend)
    passages = search(query, ingredient, top_k) if search else _local_search(ingredient, top_k)
    # Keep only passages that really concern this ingredient (fixed-size chunks may not).
    wanted = ingredient.strip().lower()
    return [p for p in passages
            if wanted in {i.strip().lower() for i in str(p.metadata.get("ingredients") or p.metadata.get("ingredient", "")).split(";")}
            and p.annex]
