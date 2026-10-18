"""The API key check in app/main.py (active only when SCANNER_API_KEY is set)."""

import importlib

from fastapi.testclient import TestClient


def _client(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("SCANNER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("SCANNER_API_KEY", key)
    import app.main

    return TestClient(importlib.reload(app.main).app)


def test_open_without_a_configured_key(monkeypatch):
    assert _client(monkeypatch, None).get("/rag/health").status_code == 200


def test_key_required_when_configured(monkeypatch):
    client = _client(monkeypatch, "s3cret")
    assert client.get("/health").status_code == 200  # Render's health check stays open
    assert client.get("/rag/health").status_code == 401
    assert client.get("/rag/health", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/rag/health", headers={"X-API-Key": "s3cret"}).status_code == 200
    _client(monkeypatch, None)  # leave app.main without a key for the other tests
