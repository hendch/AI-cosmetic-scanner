"""Single source of truth for the RAG module. Override via environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- Embeddings ---
# Swap to "BAAI/bge-m3" with: EMBEDDING_MODEL=BAAI/bge-m3 (then re-index)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
# bge v1.5 English models use a query instruction; bge-m3 does not.
QUERY_PREFIX = "" if "bge-m3" in EMBEDDING_MODEL else \
    "Represent this sentence for searching relevant passages: "

# --- Vector store ---
QDRANT_URL = os.getenv("QDRANT_URL")  # e.g. http://localhost:6333 ; None = local mode
QDRANT_PATH = str(ROOT / "data" / "qdrant")
COLLECTIONS = {                       # one collection per chunking strategy
    "fixed": "evidence_fixed",
    "structured": "evidence_structured",
}

# --- Chunking ---
FIXED_CHUNK_TOKENS = 500
FIXED_CHUNK_OVERLAP = 100

# --- Retrieval ---
TOP_K_DEFAULT = 5
MIN_SCORE = {"fixed": 0.35, "structured": 0.0}
DEFAULT_STRATEGY = "structured"

# --- Paths ---
CORPUS_RAW = ROOT / "corpus" / "raw"
CORPUS_STRUCTURED = ROOT / "corpus" / "structured"
SOURCES_YAML = ROOT / "corpus" / "sources.yaml"
EVAL_DIR = ROOT / "eval"