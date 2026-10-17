"""Team model client: an OpenAI-compatible chat endpoint configured in .env.

LLM_BASE_URL, LLM_MODEL and HF_TOKEN come from .env (never hardcoded, never committed).
Team rule: temperature 0 for agents and evaluation.
"""

import os
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class LLMError(RuntimeError):
    pass


def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def settings() -> tuple[str, str, str]:
    _load_env()
    missing = [k for k in ("LLM_BASE_URL", "LLM_MODEL", "HF_TOKEN") if not os.environ.get(k)]
    if missing:
        raise LLMError(f"Missing {', '.join(missing)} in .env (see .env.example).")
    return os.environ["LLM_BASE_URL"].rstrip("/"), os.environ["LLM_MODEL"], os.environ["HF_TOKEN"]


def chat(messages: list[dict], temperature: float = 0.0, timeout: float = 90.0) -> str:
    base_url, model, token = settings()
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": model, "messages": messages, "temperature": temperature},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"Could not reach the model endpoint: {exc}") from exc
    if response.status_code != 200:
        raise LLMError(f"Model endpoint answered HTTP {response.status_code}: {response.text[:300]}")
    return response.json()["choices"][0]["message"]["content"]


def model_name() -> str:
    return settings()[1]
