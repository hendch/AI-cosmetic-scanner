"""Regenerate samples/toxicology, samples/ethics and samples/regulatory from samples/input.

Usage: python -m scripts.generate_samples
"""

import json
from pathlib import Path

from app.common_schemas import ProductInput
from app.ethics.agent import analyze as ethics_agent
from app.regulatory.mock import build_mock_response as regulatory_mock
from app.toxicology.mock import build_mock_response as toxicology_mock

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def main() -> None:
    for agent, build in (("toxicology", toxicology_mock), ("ethics", ethics_agent), ("regulatory", regulatory_mock)):
        out_dir = SAMPLES / agent
        out_dir.mkdir(exist_ok=True)
        for input_file in sorted((SAMPLES / "input").glob("*.json")):
            payload = ProductInput.model_validate_json(input_file.read_text(encoding="utf-8"))
            response = build(payload).model_dump(mode="json")
            (out_dir / input_file.name).write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {agent}/{input_file.name}")


if __name__ == "__main__":
    main()
