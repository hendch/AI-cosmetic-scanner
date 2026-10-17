from functools import lru_cache
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from . import config

@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(config.EMBEDDING_MODEL)

@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    if config.QDRANT_URL:
        return QdrantClient(url=config.QDRANT_URL)
    return QdrantClient(path=config.QDRANT_PATH)

def embed_docs(texts: list[str]) -> list[list[float]]:
    return get_model().encode(texts, normalize_embeddings=True,
                              batch_size=32, show_progress_bar=False).tolist()

def embed_query(q: str) -> list[float]:
    return get_model().encode(config.QUERY_PREFIX + q, normalize_embeddings=True).tolist()