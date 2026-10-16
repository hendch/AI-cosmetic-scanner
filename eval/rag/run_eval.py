"""Evaluate structured and fixed-size RAG retrieval against eval/questions.csv.

Run from the project root:
    python -m eval.run_eval

The script queries existing Qdrant collections; it does not rebuild the index.
It writes eval/results.csv (per-question results) and eval/metrics.csv (aggregate).
"""
from __future__ import annotations

import csv
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.rag.retrieve import retrieve
from app.rag.schemas import RetrieveRequest

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.csv"
RESULTS_PATH = EVAL_DIR / "results.csv"
METRICS_PATH = EVAL_DIR / "metrics.csv"
TOP_K = 5

CONFIGS = (
    # Production-style structured retrieval: ingredient metadata filter enabled.
    ("structured_filtered", "structured", True),
    # Ablation: same structured collection, ingredient filter disabled.
    ("structured_unfiltered", "structured", False),
    # Fixed chunks use retrieve()'s ingredient-mention post-filter.
    ("fixed_filtered", "fixed", True),
)


def _plain(value: Any) -> str:
    """Lowercase, remove accents, and normalize whitespace for phrase matching."""
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.lower().split())


def _number_tokens(value: str) -> set[Decimal]:
    """Extract numeric values while treating decimal comma and point as equivalent."""
    found: set[Decimal] = set()
    for token in re.findall(r"(?<!\w)\d+(?:[.,]\d+)?\s*%?", value):
        token = token.strip().replace("%", "").replace(" ", "").replace(",", ".")
        try:
            found.add(Decimal(token).normalize())
        except InvalidOperation:
            pass
    return found


def _key_matches(text: str, key_text: str) -> bool:
    """Match a fixed-size chunk's key text, tolerating PDF decimal formatting."""
    key = (key_text or "").strip()
    if not key:
        return False

    # Numeric keys are matched as complete numeric tokens, not arbitrary substrings.
    numeric_key = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*%?\s*", key)
    if numeric_key:
        try:
            wanted = Decimal(numeric_key.group(1).replace(",", ".")).normalize()
            return wanted in _number_tokens(text)
        except InvalidOperation:
            return False

    normalized_text = _plain(text)
    normalized_key = _plain(key)
    if normalized_key in normalized_text:
        return True

    # Also allow a decimal comma/point difference inside mixed keys, e.g. "limit 0.5%".
    return normalized_key.replace(",", ".") in normalized_text.replace(",", ".")


def _item_value(item: Any, field: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _is_relevant(row: dict[str, str], strategy: str, item: Any) -> bool:
    expected_id = (row.get("expected_evidence_id") or "").strip()
    if not expected_id:
        return False

    if strategy == "structured":
        return _item_value(item, "evidence_id") == expected_id

    # Fixed chunks have generated IDs (FX-...), so relevance is source + key text.
    expected_source = (row.get("expected_source_id") or "").strip()
    key_text = (row.get("key_text") or "").strip()
    metadata = _item_value(item, "metadata", {}) or {}
    source_id = metadata.get("source_id", "") if isinstance(metadata, dict) else ""
    item_text = str(_item_value(item, "text", ""))
    return bool(
        expected_source
        and key_text
        and source_id == expected_source
        and _key_matches(item_text, key_text)
    )


def _load_questions() -> list[dict[str, str]]:
    if not QUESTIONS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {QUESTIONS_PATH}. Create eval/questions.csv before running evaluation."
        )
    with QUESTIONS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "id", "question", "ingredient", "expected_evidence_id",
            "expected_source_id", "key_text", "type",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"questions.csv is missing columns: {', '.join(sorted(missing))}")
        rows = []
        for raw in reader:
            row = {key: (value or "").strip() for key, value in raw.items() if key}
            if row.get("id") and row.get("question") and row.get("ingredient"):
                rows.append(row)
        if not rows:
            raise ValueError("questions.csv contains no usable question rows.")
        return rows


def _is_coverage_question(row: dict[str, str]) -> bool:
    kind = _plain(row.get("type", ""))
    return not (row.get("expected_evidence_id") or "").strip() or "not covered" in kind


def _evaluate_one(row: dict[str, str], label: str, strategy: str, use_filter: bool) -> dict[str, Any]:
    req = RetrieveRequest(
        ingredient=row["ingredient"],
        query=row["question"],
        strategy=strategy,
        top_k=TOP_K,
    )
    try:
        response = retrieve(req, use_filter=use_filter)
        items = list(response.results)
        relevant_ranks = [
            rank for rank, item in enumerate(items, start=1)
            if _is_relevant(row, strategy, item)
        ]
        coverage_question = _is_coverage_question(row)
        expected_uncovered = coverage_question
        covered = bool(response.covered)
        coverage_pass = (not covered) if expected_uncovered else ""
        reciprocal_rank = (1.0 / relevant_ranks[0]) if relevant_ranks and not coverage_question else (0.0 if not coverage_question else "")

        result: dict[str, Any] = {
            "question_id": row["id"],
            "question": row["question"],
            "ingredient": row["ingredient"],
            "type": row.get("type", ""),
            "configuration": label,
            "strategy": strategy,
            "use_filter": use_filter,
            "expected_evidence_id": row.get("expected_evidence_id", ""),
            "expected_source_id": row.get("expected_source_id", ""),
            "key_text": row.get("key_text", ""),
            "covered": covered,
            "coverage_question": coverage_question,
            "coverage_pass": coverage_pass,
            "returned_count": len(items),
            "returned_evidence_ids": " | ".join(str(_item_value(x, "evidence_id")) for x in items),
            "returned_source_ids": " | ".join(
                str((_item_value(x, "metadata", {}) or {}).get("source_id", "")) for x in items
            ),
            "relevant_ranks": " | ".join(map(str, relevant_ranks)),
            "hit_at_3": (any(rank <= 3 for rank in relevant_ranks) if not coverage_question else ""),
            "hit_at_5": (any(rank <= 5 for rank in relevant_ranks) if not coverage_question else ""),
            "reciprocal_rank": reciprocal_rank,
            "top_result_text": str(_item_value(items[0], "text", ""))[:500] if items else "",
            "error": "",
        }
        return result
    except Exception as exc:  # Continue the full evaluation and expose the error in results.csv.
        return {
            "question_id": row["id"], "question": row["question"],
            "ingredient": row["ingredient"], "type": row.get("type", ""),
            "configuration": label, "strategy": strategy, "use_filter": use_filter,
            "expected_evidence_id": row.get("expected_evidence_id", ""),
            "expected_source_id": row.get("expected_source_id", ""),
            "key_text": row.get("key_text", ""), "covered": "", "coverage_question": _is_coverage_question(row),
            "coverage_pass": "", "returned_count": "", "returned_evidence_ids": "",
            "returned_source_ids": "", "relevant_ranks": "", "hit_at_3": "", "hit_at_5": "",
            "reciprocal_rank": "", "top_result_text": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    # Keep a stable, useful column order based on the first row.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _aggregate(results: list[dict[str, Any]], questions: list[dict[str, str]]) -> list[dict[str, Any]]:
    metrics = []
    for label, _strategy, _use_filter in CONFIGS:
        rows = [r for r in results if r["configuration"] == label and not r.get("error")]
        ranking_ids = {
            q["id"] for q in questions if not _is_coverage_question(q)
        }
        ranking_rows = [r for r in rows if r["question_id"] in ranking_ids]
        n = len(ranking_rows)
        valid3 = [r for r in ranking_rows if r["hit_at_3"] != ""]
        valid5 = [r for r in ranking_rows if r["hit_at_5"] != ""]
        valid_rr = [r for r in ranking_rows if r["reciprocal_rank"] != ""]
        coverage_rows = [r for r in rows if r["coverage_question"]]
        coverage_scored = [r for r in coverage_rows if r["coverage_pass"] != ""]
        errors = sum(1 for r in results if r["configuration"] == label and r.get("error"))
        metrics.append({
            "configuration": label,
            "ranking_questions": n,
            "Recall@3": round(sum(bool(r["hit_at_3"]) for r in valid3) / len(valid3), 4) if valid3 else "",
            "Recall@5": round(sum(bool(r["hit_at_5"]) for r in valid5) / len(valid5), 4) if valid5 else "",
            "MRR": round(sum(float(r["reciprocal_rank"]) for r in valid_rr) / len(valid_rr), 4) if valid_rr else "",
            "coverage_questions": len(coverage_rows),
            "coverage_accuracy": round(sum(bool(r["coverage_pass"]) for r in coverage_scored) / len(coverage_scored), 4) if coverage_scored else "",
            "coverage_scored": len(coverage_scored),
            "errors": errors,
        })
    return metrics


def main() -> int:
    try:
        questions = _load_questions()
    except Exception as exc:
        print(f"ERROR loading questions: {exc}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    total = len(questions) * len(CONFIGS)
    print(f"Evaluating {len(questions)} questions across {len(CONFIGS)} configurations ({total} retrievals).")
    print("Using existing Qdrant collections; indexing will not be run.\n")

    for label, strategy, use_filter in CONFIGS:
        print(f"[{label}]")
        for index, row in enumerate(questions, start=1):
            result = _evaluate_one(row, label, strategy, use_filter)
            results.append(result)
            if result.get("error"):
                print(f"  {row['id']}: ERROR — {result['error']}")
            elif result["coverage_question"]:
                print(f"  {row['id']}: covered={result['covered']} coverage_pass={result['coverage_pass']}")
            else:
                print(f"  {row['id']}: hit@3={result['hit_at_3']} hit@5={result['hit_at_5']} RR={result['reciprocal_rank']}")
        print()

    metrics = _aggregate(results, questions)
    _write_csv(RESULTS_PATH, results)
    _write_csv(METRICS_PATH, metrics)

    print(f"Per-question results: {RESULTS_PATH}")
    print(f"Aggregate metrics:    {METRICS_PATH}\n")
    print("Summary:")
    for row in metrics:
        print(
            f"  {row['configuration']}: Recall@3={row['Recall@3']} "
            f"Recall@5={row['Recall@5']} MRR={row['MRR']} "
            f"coverage_accuracy={row['coverage_accuracy']} errors={row['errors']}"
        )

    if any(row.get("error") for row in results):
        print("\nSome queries failed. Inspect the error column in eval/results.csv.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
