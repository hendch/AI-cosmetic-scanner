"""Make the tests independent of each developer's .env and local data/ folder."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def offline_sources(monkeypatch):
    # The real PETA list is local and gitignored: tests use a small fixed copy.
    monkeypatch.setenv("PETA_BRANDS_PATH", str(FIXTURES / "peta_brands.json"))
    # RETRIEVAL_BACKEND=rag (the .env.example default) opens data/qdrant, which a running server may hold locked.
    monkeypatch.setenv("RETRIEVAL_BACKEND", "local")
