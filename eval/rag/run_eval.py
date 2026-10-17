"""Retrieval evaluation: structured vs fixed chunking.

Run from the project root, with uvicorn STOPPED (Qdrant local mode = one process):
    python eval/run_eval.py

Reads  eval/questions.csv  (id,question,ingredient,expected_evidence_id,expected_source_id,key_text,type)
Writes eval/results.csv (summary) and eval/results_per_question.csv.

Two hit definitions are reported for every configuration:
  STRICT  : the chunk is the expected record, OR comes from the expected source and contains
            the key value and the ingredient name. Measures retrieval of the PRIMARY source.
  LENIENT : the chunk is the expected record, OR contains the key value and the ingredient
            name, from ANY source. Measures whether the ANSWER is retrievable at all.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from app.rag import config, ingest  # noqa: E402
from app.rag.chunkers import record_id  # noqa: E402
from app.rag.retrieve import retrieve, IndexNotBuilt  # noqa: E402
from app.rag.schemas import RetrieveRequest  # noqa: E402
from app.rag.store import get_client  # noqa: E402

K = 10  # retrieve 10; report Recall@3, Recall@5, MRR@10
QUESTIONS = config.EVAL_DIR / "questions.csv"

# (label, strategy, use_ingredient_filter)
CONFIGS = [
    ("structured + filter", "structured", True),     # what the API does
    ("structured, no filter", "structured", False),  # isolates the chunking effect
    ("fixed + name post-filter", "fixed", True),     # baseline as built
    ("fixed, no filter", "fixed", False),            # pure baseline
]


def squash(s: str) -> str:
    """Lowercase, drop soft hyphens, decimal comma -> dot, remove all whitespace."""
    return "".join(str(s).lower().replace("\xad", "").replace(",", ".").split())


def name_tokens(ingredient: str) -> list[str]:
    return [squash(t) for t in ingredient.replace("(", " ").replace(")", " ").split() if len(t) >= 4]


def is_hit(item, row, lenient: bool) -> bool:
    if row["expected_evidence_id"] and item.evidence_id == row["expected_evidence_id"]:
        return True
    if not row["key_text"]:
        return False
    if not lenient:
        if not row["expected_source_id"] or item.metadata.get("source_id") != row["expected_source_id"]:
            return False
    text = squash(item.text)
    if squash(row["key_text"]) not in text:
        return False
    toks = name_tokens(row["ingredient"])
    return any(t in text for t in toks) if toks else True


def first_rank(results, row, lenient):
    for i, item in enumerate(results, 1):
        if is_hit(item, row, lenient):
            return i
    return None


def metrics(ranks: pd.Series) -> tuple:
    r3 = (ranks.le(3) & ranks.notna()).mean()
    r5 = (ranks.le(5) & ranks.notna()).mean()
    mrr = ranks.map(lambda r: 1 / r if pd.notna(r) else 0).mean()
    return round(r3, 3), round(r5, 3), round(mrr, 3)


def main():
    df = pd.read_csv(QUESTIONS, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df = df[df["question"].str.strip() != ""].reset_index(drop=True)

    known = {record_id(r) for r in ingest.load_structured()}
    for _, r in df.iterrows():
        if r["expected_evidence_id"] and r["expected_evidence_id"] not in known:
            print(f"WARNING {r['id']}: expected_evidence_id '{r['expected_evidence_id']}' is not in the corpus")

    try:  # warm-up so the first configuration is not charged for model/DB start-up
        for s in ("structured", "fixed"):
            retrieve(RetrieveRequest(ingredient="warmup", query="warmup", top_k=1, strategy=s))
    except IndexNotBuilt as e:
        sys.exit(f"{e}\n(Run: python -m app.rag.index, with uvicorn stopped)")

    rows = []
    for label, strategy, use_filter in CONFIGS:
        for _, q in df.iterrows():
            req = RetrieveRequest(ingredient=q["ingredient"], query=q["question"], top_k=K, strategy=strategy)
            t0 = time.perf_counter()
            resp = retrieve(req, use_filter=use_filter)
            ms = (time.perf_counter() - t0) * 1000
            answerable = bool(q["expected_evidence_id"] or q["expected_source_id"])
            rows.append({
                "config": label, "id": q["id"], "type": q["type"], "ingredient": q["ingredient"],
                "answerable": answerable, "covered_returned": resp.covered, "n_results": len(resp.results),
                "rank_strict": first_rank(resp.results, q, False) if answerable else None,
                "rank_lenient": first_rank(resp.results, q, True) if answerable else None,
                "top1_id": resp.results[0].evidence_id if resp.results else "",
                "top1_score": resp.results[0].score if resp.results else None,
                "ms": round(ms, 1),
            })

    per_q = pd.DataFrame(rows)
    per_q.to_csv(config.EVAL_DIR / "results_per_question.csv", index=False)

    summary = []
    for label, _, _ in CONFIGS:
        d = per_q[per_q["config"] == label]
        ans, nc = d[d["answerable"]], d[~d["answerable"]]
        s3, s5, sm = metrics(ans["rank_strict"])
        l3, l5, lm = metrics(ans["rank_lenient"])
        summary.append({
            "config": label, "n": len(ans),
            "strict R@3": s3, "strict R@5": s5, "strict MRR": sm,
            "lenient R@3": l3, "lenient R@5": l5, "lenient MRR": lm,
            "not_covered_ok": f"{int((~nc['covered_returned']).sum())}/{len(nc)}" if len(nc) else "n/a",
            "avg_ms": round(d["ms"].mean(), 1),
        })
    res = pd.DataFrame(summary)
    res.to_csv(config.EVAL_DIR / "results.csv", index=False)

    pd.set_option("display.width", 220)
    print("\n=== SUMMARY ===")
    print(res.to_string(index=False))
    order = [c[0] for c in CONFIGS]
    for col, name in (("rank_strict", "STRICT (right source)"), ("rank_lenient", "LENIENT (answer present, any source)")):
        view = per_q.assign(r=per_q.apply(
            lambda x: "n/a" if not x["answerable"] else ("" if pd.isna(x[col]) else int(x[col])), axis=1))
        print(f"\n=== FIRST-HIT RANK, {name} (blank = miss) ===")
        print(view.pivot(index="id", columns="config", values="r")[order].to_string())

    print("\n=== LENIENT MISSES (real failures to describe in the report) ===")
    miss = per_q[per_q["answerable"] & per_q["rank_lenient"].isna()]
    print(miss[["config", "id", "type", "n_results", "top1_id", "top1_score"]].to_string(index=False) if len(miss) else "none")
    print(f"\nSaved: {config.EVAL_DIR / 'results.csv'} and results_per_question.csv")
    get_client().close()


if __name__ == "__main__":
    main()