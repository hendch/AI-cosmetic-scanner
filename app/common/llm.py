"""Shared model client and prompt loading for every agent.

One OpenAI-compatible chat endpoint, configured in .env (see .env.example):
    LLM_BASE_URL=https://router.huggingface.co/v1
    LLM_MODEL=Qwen/Qwen2.5-7B-Instruct:featherless-ai
    HF_TOKEN=...                       (or LLM_API_KEY)
    LLM_TIMEOUT=90                     (seconds, optional)
Local Ollama: LLM_BASE_URL=http://localhost:11434/v1, LLM_MODEL=qwen2.5:7b (no token needed).
Team rule: temperature 0 for agents and evaluation.

Importing this module loads .env; real environment variables win.
"""

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"
DEFAULT_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct:featherless-ai"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


class LLMError(RuntimeError):
    pass


# --- prompts ---------------------------------------------------------------

@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    user: str
    temperature: float
    max_tokens: int

    def render(self, **fields: str) -> list[dict]:
        user = self.user
        for k, v in fields.items():
            user = user.replace("{" + k + "}", v)
        return [{"role": "system", "content": self.system}, {"role": "user", "content": user}]


@lru_cache(maxsize=32)
def load_prompt(agent: str, version: str) -> Prompt:
    """prompts/<agent>/<version>.yaml"""
    path = PROMPTS_DIR / agent / f"{version}.yaml"
    if not path.exists():
        raise LLMError(f"Unknown prompt {agent}/{version}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    params = data.get("model_params", {})
    return Prompt(version=data["version"], system=data["system"], user=data["user"],
                  temperature=float(params.get("temperature", 0)), max_tokens=int(params.get("max_tokens", 700)))


# --- model -----------------------------------------------------------------

def model_name() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)


def settings() -> tuple[str, str, str]:
    """(base_url, model, api_key)"""
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.environ.get("HF_TOKEN") or os.environ.get("LLM_API_KEY")
    if not api_key:
        if "localhost" in base_url or "127.0.0.1" in base_url:
            api_key = "ollama"  # local Ollama ignores the key
        else:
            raise LLMError("No LLM token found. Create .env in the repo root (copy .env.example) and set HF_TOKEN.")
    return base_url, model_name(), api_key


def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int | None = None,
         timeout: float | None = None) -> str:
    """One chat completion; returns the raw text answer. One retry on network errors, 429 and 5xx."""
    base_url, model, api_key = settings()
    body = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        body["max_tokens"] = max_tokens
    timeout = timeout or float(os.environ.get("LLM_TIMEOUT", "90"))
    problem = ""
    for _ in range(2):
        try:
            r = httpx.post(f"{base_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                           json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            problem = f"Could not reach the model endpoint: {exc}"
            continue
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"] or ""
        problem = f"Model endpoint answered HTTP {r.status_code}: {r.text[:300]}"
        if r.status_code != 429 and r.status_code < 500:
            break
    raise LLMError(problem)


# A chat function takes messages + temperature + max_tokens and returns the raw text answer.
# Agents accept one as a parameter so tests can pass a fake model.
ChatFn = Callable[[list[dict], float, int], str]


def chat_function() -> ChatFn:
    settings()  # fail fast when the token is missing
    return lambda messages, temperature, max_tokens: chat(messages, temperature, max_tokens)


# --- answers ---------------------------------------------------------------

def parse_json_object(text: str) -> dict:
    """Extract the first JSON object from a model answer (tolerates ``` fences and chatter)."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in answer")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj = json.loads(text[start : i + 1])
                if not isinstance(obj, dict):
                    raise ValueError("answer is not a JSON object")
                return obj
    raise ValueError("unterminated JSON object")
