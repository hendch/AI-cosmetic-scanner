"""Embeddings and the Qdrant vector store.

Embeddings: EMBEDDING_BACKEND=hf (default) calls the Hugging Face router with HF_TOKEN, so
the API needs no torch. EMBEDDING_BACKEND=local uses sentence-transformers (dev, index builds).
Both return the same vectors for BAAI/bge-small-en-v1.5 (checked: cosine 1.000000).

Vector store, in order: QDRANT_URL (server) -> data/qdrant (local build) -> the exported index
in corpus/index/, loaded into an in-memory Qdrant (deployment: no disk needed).
"""

import json
import os
from functools import lru_cache

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.common import llm  # loads .env and holds the HF token settings
from . import config


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer  # dev only: not in the API image

    return SentenceTransformer(config.EMBEDDING_MODEL)


def _embed_hf(texts: list[str]) -> list[list[float]]:
    _, _, token = llm.settings()
    url = f"{config.HF_EMBEDDING_URL}/{config.EMBEDDING_MODEL}/pipeline/feature-extraction"
    try:
        r = httpx.post(url, headers={"Authorization": f"Bearer {token}"}, json={"inputs": texts},
                       timeout=float(os.environ.get("LLM_TIMEOUT", "90")))
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise llm.LLMError(f"Embedding call failed: {exc}") from exc
    vecs = r.json()
    out = []
    for v in vecs:
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / norm for x in v])
    return out


def embed_docs(texts: list[str]) -> list[list[float]]:
    if config.EMBEDDING_BACKEND == "local":
        return get_model().encode(texts, normalize_embeddings=True, batch_size=32,
                                  show_progress_bar=False).tolist()
    return [v for i in range(0, len(texts), 32) for v in _embed_hf(texts[i:i + 32])]


def embed_query(q: str) -> list[float]:
    return embed_docs([config.QUERY_PREFIX + q])[0]


def _load_exported(client: QdrantClient) -> None:
    for name in config.SHIPPED_COLLECTIONS:
        path = config.INDEX_EXPORT_DIR / f"{config.COLLECTIONS[name]}.jsonl"
        if not path.exists():
            continue
        points = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        client.create_collection(config.COLLECTIONS[name],
                                 vectors_config=VectorParams(size=len(points[0]["vector"]), distance=Distance.COSINE))
        client.upsert(config.COLLECTIONS[name],
                      [PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points])


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    if config.QDRANT_URL:
        return QdrantClient(url=config.QDRANT_URL)
    if os.path.isdir(config.QDRANT_PATH):
        return QdrantClient(path=config.QDRANT_PATH)
    client = QdrantClient(":memory:")
    _load_exported(client)
    return client
