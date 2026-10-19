"""POST /toxicology/analyze

TOXICOLOGY_MODE selects the implementation:
- "live": retrieval + LLM + validation. Default when HF_TOKEN or LLM_API_KEY is set.
- "mock": retrieval + rules only, no LLM call (no credits). Default otherwise, and used by the tests.

?prompt_version=v3 picks prompts/toxicology/v3.yaml for one request (benchmarking prompt versions);
without it, TOXICOLOGY_PROMPT_VERSION, else v7.
"""

import os

from fastapi import APIRouter, HTTPException

from app.common import llm  # noqa: F401  loads .env, so TOXICOLOGY_MODE and HF_TOKEN from .env reach _mode()
from app.common.llm import LLMError
from app.common_schemas import ProductInput
from app.toxicology.agent import analyze as run_agent
from app.toxicology.agent import load_prompt
from app.toxicology.schemas import ToxicologyResponse

router = APIRouter(prefix="/toxicology", tags=["toxicology"])


def _mode() -> str:
    default = "live" if (os.environ.get("HF_TOKEN") or os.environ.get("LLM_API_KEY")) else "mock"
    return os.environ.get("TOXICOLOGY_MODE", default)


@router.post("/analyze", response_model=ToxicologyResponse)
def analyze(payload: ProductInput, prompt_version: str | None = None) -> ToxicologyResponse:
    if _mode() != "live":
        return run_agent(payload, mode="rules")
    try:
        prompt = load_prompt(prompt_version)
    except LLMError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return run_agent(payload, prompt=prompt)
