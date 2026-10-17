"""The only place the regulatory agent asks for evidence.

Expected contract with the retrieval service (Haroun), see docs/regulatory_interfaces.md:

    POST {RETRIEVAL_URL}/retrieval/search
    {"query": str, "filters": {"doc_type": "regulation", "ingredient": str}, "top_k": int}
    -> {"results": [{"chunk_id", "source_id", "text", "score",
                     "metadata": {"ingredient", "annex", "entry", ...condition fields}}]}

RETRIEVAL_BACKEND selects the implementation:
- "local" (default): placeholder that answers from corpus/regulatory/ in the same format.
- "http": calls Haroun's service at RETRIEVAL_URL.
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


def _http_search(query: str, ingredient: str, top_k: int) -> list[Passage]:
    url = os.environ.get("RETRIEVAL_URL", "").rstrip("/")
    if not url:
        raise RetrievalError("RETRIEVAL_BACKEND=http but RETRIEVAL_URL is not set")
    body = {"query": query, "filters": {"doc_type": "regulation", "ingredient": ingredient}, "top_k": top_k}
    try:
        r = httpx.post(f"{url}/retrieval/search", json=body, timeout=30)
        r.raise_for_status()
        results = r.json().get("results", [])
    except (httpx.HTTPError, ValueError) as e:
        raise RetrievalError(f"retrieval service failed: {e}") from e
    return [Passage(chunk_id=x.get("chunk_id", x["source_id"]), source_id=x["source_id"], text=x.get("text", ""),
                    score=float(x.get("score", 0.0)), metadata=x.get("metadata", {})) for x in results]


def search_regulation(ingredient: str, product_type: str | None = None, top_k: int = 5) -> list[Passage]:
    """Regulation passages about one ingredient. Empty list = nothing found."""
    query = f"{ingredient} restrictions conditions of use" + (f" {product_type.replace('_', '-')}" if product_type else "")
    backend = os.environ.get("RETRIEVAL_BACKEND", "local")
    passages = _http_search(query, ingredient, top_k) if backend == "http" else _local_search(ingredient, top_k)
    # Keep only passages that really concern this ingredient (fixed-size chunks may not).
    wanted = ingredient.strip().lower()
    return [p for p in passages
            if wanted in {i.strip().lower() for i in str(p.metadata.get("ingredients") or p.metadata.get("ingredient", "")).split(";")}
            and p.annex]
