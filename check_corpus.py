import collections
from app.rag import config, ingest
from app.rag.chunkers import record_id

sources = ingest.load_sources()
records = ingest.load_structured()      # also checks required fields
errors = []

for sid, s in sources.items():
    for k in ("title", "date", "url"):
        if not s.get(k) or "TODO" in str(s[k]):
            errors.append(f"source '{sid}': '{k}' missing or TODO")
    if not s.get("file"):
        errors.append(f"source '{sid}': no raw file (fixed baseline needs one)")
    elif not (config.CORPUS_RAW / s["file"]).exists():
        errors.append(f"source '{sid}': file not found in corpus/raw/: {s['file']}")

ids = collections.Counter(record_id(r) for r in records)
errors += [f"duplicate id: {i}" for i, n in ids.items() if n > 1]

for r in records:
    label = r.get("id") or r["ingredient"]
    if r["source_id"] not in sources:
        errors.append(f"{label}: unknown source_id '{r['source_id']}'")
    if any("TODO" in str(v) or "FIXTURE" in str(v) for v in r.values()):
        errors.append(f"{label}: contains TODO/FIXTURE")

by_ing = collections.Counter(r["ingredient"] for r in records)
print(f"{len(records)} records, {len(by_ing)} ingredients, {len(sources)} sources")
for ing, n in sorted(by_ing.items()):
    print(f"  {ing}: {n}")
print("\nERRORS:" if errors else "\nCorpus OK")
for e in errors:
    print(" -", e)