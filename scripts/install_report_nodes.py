"""Install Omar's report & validation nodes into the n8n workflow file.

Writes deploy/n8n/nodes/report/*.js into the matching Code nodes and the chosen
prompts/validator/<version>.yaml into the Validator Agent. Only those nodes change.

Usage: python -m scripts.install_report_nodes <workflow.json> [--validator v2]
"""

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NODES_DIR = ROOT / "deploy" / "n8n" / "nodes" / "report"
PROMPTS_DIR = ROOT / "prompts" / "validator"

CODE_NODES = {
    "Live - Build draft": "build_draft.js",
    "Live - Parse validator": "parse_validator.js",
    "Live - Final evidence gate": "final_evidence_gate.js",
    "Live - Public result": "public_result.js",
}
VALIDATOR_AGENT = "Live - Validator Agent"
VALIDATOR_MODEL = "Live - Validator Agent - Chat Model"


def install(workflow: dict, validator_version: str) -> list[str]:
    nodes = {n["name"]: n for n in workflow["nodes"]}
    missing = [name for name in [*CODE_NODES, VALIDATOR_AGENT, VALIDATOR_MODEL] if name not in nodes]
    if missing:
        raise SystemExit(f"Workflow is missing nodes: {', '.join(missing)}")

    for name, filename in CODE_NODES.items():
        nodes[name]["parameters"]["jsCode"] = (NODES_DIR / filename).read_text(encoding="utf-8")

    prompt = yaml.safe_load((PROMPTS_DIR / f"{validator_version}.yaml").read_text(encoding="utf-8"))
    agent = nodes[VALIDATOR_AGENT]["parameters"]
    agent["text"] = prompt["user"].strip()
    agent.setdefault("options", {})["systemMessage"] = prompt["system"].strip()

    params = prompt["model_params"]
    model = nodes[VALIDATOR_MODEL]["parameters"]
    model["model"] = params["model"]
    model.setdefault("options", {}).update(temperature=params["temperature"], numCtx=params["num_ctx"])

    return [*CODE_NODES, VALIDATOR_AGENT, VALIDATOR_MODEL]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workflow", type=Path)
    parser.add_argument("--validator", default="v2", help="prompt version in prompts/validator (default v2)")
    args = parser.parse_args()

    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    changed = install(workflow, args.validator)
    # Same formatting as the exported workflow, so only the installed nodes show up in the diff.
    args.workflow.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Installed validator {args.validator} and {len(changed)} nodes: {', '.join(changed)}")


if __name__ == "__main__":
    main()
