"""Label OCR: a photo of the ingredient list -> the ingredient names as printed.

A vision model reads the photo (OCR_MODEL, default Qwen/Qwen3-VL-30B-A3B-Instruct, through the same
Hugging Face router and HF_TOKEN as the agents). It only copies text; turning the names into INCI
ingredients is done afterwards by app/ingestion/normalize.py. The prompt is prompts/ocr/v1.yaml.
"""

import base64
import io
import os

import yaml
from PIL import Image, ImageOps
from pydantic import BaseModel, ValidationError

from app.common import llm

DEFAULT_MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"
PROMPT_VERSION = os.environ.get("OCR_PROMPT_VERSION", "v1")
MAX_SIDE = 1600  # pixels: enough to read small print, keeps the request (and credits) small


class OcrError(RuntimeError):
    pass


class OcrResult(BaseModel):
    readable: bool
    ingredients: list[str] = []
    uncertain: list[str] = []
    brand: str | None = None
    product_name: str | None = None
    product_type: str | None = None


def ocr_model() -> str:
    return os.environ.get("OCR_MODEL", DEFAULT_MODEL)


def _prompt() -> dict:
    path = llm.PROMPTS_DIR / "ocr" / f"{PROMPT_VERSION}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def prepare_image(data: bytes) -> str:
    """Any photo -> a JPEG data URI, rotated upright (phone EXIF), at most MAX_SIDE pixels."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception as exc:  # PIL raises several types for non-images
        raise OcrError(f"The file is not a readable image: {exc}") from exc
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def read_label(data: bytes) -> OcrResult:
    """One model call (plus one retry if the answer is not the expected JSON)."""
    prompt = _prompt()
    params = prompt.get("model_params", {})
    messages = [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": [
            {"type": "text", "text": prompt["user"]},
            {"type": "image_url", "image_url": {"url": prepare_image(data)}},
        ]},
    ]
    problem = ""
    for _ in range(2):
        answer = llm.chat(messages, temperature=float(params.get("temperature", 0)),
                          max_tokens=int(params.get("max_tokens", 1500)), model=ocr_model())
        try:
            return OcrResult.model_validate(llm.parse_json_object(answer))
        except (ValueError, ValidationError) as exc:
            problem = str(exc)[:200]
            messages += [{"role": "assistant", "content": answer},
                         {"role": "user", "content": f"That was not the requested JSON ({problem}). Return only the JSON object."}]
    raise OcrError(f"The OCR model did not return the expected JSON: {problem}")
