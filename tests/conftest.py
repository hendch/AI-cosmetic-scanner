"""Settings for every test, whatever is in your .env: tests run offline and never spend credits.

Set before the app is imported; app/common/llm.py loads .env without overriding these.
Tests that need another setting change it themselves (monkeypatch.setenv).
"""

import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

os.environ["REGULATORY_MODE"] = "mock"  # rules only, no LLM calls
os.environ["TOXICOLOGY_MODE"] = "mock"  # retrieval + rules only, no LLM calls
os.environ["RETRIEVAL_BACKEND"] = "local"  # read the corpus CSVs, no embedding calls
os.environ["EMBEDDING_BACKEND"] = "local"  # never call the embedding API from a test
os.environ["SCANNER_API_KEY"] = ""  # set, not removed: loading .env later never overrides it, whatever the import order  # the API stays open inside tests (tests/test_main_auth.py sets its own)
os.environ["PETA_BRANDS_PATH"] = str(FIXTURES / "peta_brands.json")  # the real list is local and gitignored
