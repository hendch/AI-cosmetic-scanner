from qdrant_client.models import Filter, FieldCondition, MatchAny

from . import config
from .chunkers import norm
from .schemas import RetrieveRequest, RetrieveResponse, EvidenceItem
from .store import get_client, embed_query


class IndexNotBuilt(RuntimeError):
    pass


def _to_item(p) -> EvidenceItem:
    pl = p.payload
    keys = ("ingredient", "status", "product_type", "max_concentration", "entry_ref", "source_id",
            # annex entries (doc_type "regulation"): what the regulatory agent needs to rebuild the entry
            "doc_type", "ingredients", "annex", "entry", "product_type_body_parts", "other_conditions",
            "warnings", "inci_names", "chemical_name", "cas", "consolidated_version", "source_url")
    meta = {k: pl.get(k) for k in keys if pl.get(k) is not None}
    return EvidenceItem(evidence_id=pl["evidence_id"], text=pl["text"],
                        score=round(float(p.score), 4), source=pl["source"],
                        section=pl.get("section"), source_date=pl.get("source_date"),
                        url=pl.get("url"), metadata=meta)


def retrieve(req: RetrieveRequest, use_filter: bool = True) -> RetrieveResponse:
    """use_filter=False disables ingredient filtering (useful for the eval ablation)."""
    client = get_client()
    coll = config.COLLECTIONS[req.strategy]
    if not client.collection_exists(coll):
        raise IndexNotBuilt(f"Collection '{coll}' missing. Run: python -m app.rag.index")

    name = norm(req.ingredient)
    vec = embed_query(f"{req.ingredient}: {req.query}")

    if req.strategy == "structured":
        flt = Filter(must=[FieldCondition(key="names", match=MatchAny(any=[name]))]) \
            if use_filter else None
        points = client.query_points(coll, query=vec, query_filter=flt,
                                     limit=req.top_k, with_payload=True).points
    else:
        # Fixed chunks carry no ingredient metadata, so over-fetch then keep
        # only chunks that actually mention the ingredient.
        points = client.query_points(coll, query=vec, limit=req.top_k * 4,
                                     with_payload=True).points
        if use_filter:
            points = [p for p in points if name in norm(p.payload["text"])]
        points = points[:req.top_k]

    points = [p for p in points if p.score >= config.MIN_SCORE[req.strategy]]
    return RetrieveResponse(ingredient=req.ingredient, strategy=req.strategy,
                            covered=bool(points), results=[_to_item(p) for p in points])