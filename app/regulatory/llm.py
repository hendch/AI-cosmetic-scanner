"""LLM access and prompt loading for the regulatory agent.

Uses the OpenAI-compatible chat API, configured in .env:
    LLM_BASE_URL=https://router.huggingface.co/v1
    LLM_MODEL=Qwen/Qwen2.5-7B-Instruct:featherless-ai
    HF_TOKEN=...                       (API key)
    REGULATORY_PROMPT_VERSION=v4
Switching to local Ollama: LLM_BASE_URL=http://localhost:11434/v1, LLM_MODEL=qwen2.5:7b.
"""

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import yaml

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "regulatory"

try:  # .env is optional; real environment variables win
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


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


@lru_cache(maxsize=8)
def load_prompt(version: str | None = None) -> Prompt:
    version = version or os.environ.get("REGULATORY_PROMPT_VERSION", "v4")
    data = yaml.safe_load((PROMPTS_DIR / f"{version}.yaml").read_text(encoding="utf-8"))
    params = data.get("model_params", {})
    return Prompt(version=data["version"], system=data["system"], user=data["user"],
                  temperature=float(params.get("temperature", 0)), max_tokens=int(params.get("max_tokens", 700)))


# A chat function takes messages + params and returns the raw text answer.
ChatFn = Callable[[list[dict], float, int], str]


def openai_chat() -> ChatFn:
    from openai import OpenAI

    api_key = os.environ.get("HF_TOKEN") or os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL", "https://router.huggingface.co/v1")
    if not api_key:
        if "localhost" in base_url or "127.0.0.1" in base_url:
            api_key = "ollama"  # local Ollama ignores the key
        else:
            raise RuntimeError(
                "No LLM token found. Create a .env file in the repo root (copy .env.example) and set HF_TOKEN, "
                "or run with REGULATORY_MODE=mock / --mode mock."
            )
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=float(os.environ.get("LLM_TIMEOUT", "60")),
        max_retries=1,
    )
    model = os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct:featherless-ai")

    def chat(messages: list[dict], temperature: float, max_tokens: int) -> str:
        r = client.chat.completions.create(model=model, messages=messages, temperature=temperature,
                                           max_tokens=max_tokens)
        return r.choices[0].message.content or ""

    return chat


def model_name() -> str:
    return os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct:featherless-ai")


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
