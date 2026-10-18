import json
import uuid
from qdrant_client.models import VectorParams, Distance, PointStruct

from . import config, ingest, chunkers
from .store import get_client, get_model, embed_docs


def _recreate(client, name, dim):
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))


def _upsert(client, name, chunks):
    for i in range(0, len(chunks), 64):
        batch = chunks[i:i + 64]
        vecs = embed_docs([c.text for c in batch])
        client.upsert(name, [
            PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, c.evidence_id)),
                        vector=v, payload=c.payload)
            for c, v in zip(batch, vecs)])


def build():
    sources = ingest.load_sources()
    records = ingest.load_structured()
    docs = ingest.load_documents(records, sources)
    model, client = get_model(), get_client()
    dim = model.get_embedding_dimension()

    # Strategy B: structured
    from app.regulatory.kb import load_kb

    s_chunks = [chunkers.structured(r, sources) for r in records]
    s_chunks += [chunkers.annex_row(row) for row in load_kb().rows]
    _recreate(client, config.COLLECTIONS["structured"], dim)
    _upsert(client, config.COLLECTIONS["structured"], s_chunks)

    # Strategy A: fixed-size
    f_chunks = []
    for d in docs:
        src = sources[d["source_id"]]
        for n, text in enumerate(chunkers.fixed(d["text"], model.tokenizer)):
            eid = f"FX-{d['source_id']}-{n:03d}"
            f_chunks.append(chunkers.Chunk(eid, text, {
                "evidence_id": eid, "text": text, "strategy": "fixed",
                "source_id": d["source_id"], "source": src["title"],
                "section": None, "source_date": src.get("date"), "url": src.get("url")}))
    _recreate(client, config.COLLECTIONS["fixed"], dim)
    _upsert(client, config.COLLECTIONS["fixed"], f_chunks)

    export(client)
    print(f"model={config.EMBEDDING_MODEL} dim={dim}")
    print(f"structured: {len(s_chunks)} chunks ({len(records)} records + {len(s_chunks) - len(records)} annex entries)")
    print(f"fixed:      {len(f_chunks)} chunks from {len(docs)} documents "
          f"({', '.join(sorted({d['origin'] for d in docs}))})")


def export(client) -> None:
    """Write the shipped collections to corpus/index/ so the API can load them without a disk."""
    config.INDEX_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for name in config.SHIPPED_COLLECTIONS:
        coll = config.COLLECTIONS[name]
        points, offset = [], None
        while True:
            batch, offset = client.scroll(coll, limit=256, offset=offset, with_vectors=True, with_payload=True)
            points += batch
            if offset is None:
                break
        lines = [json.dumps({"id": str(p.id), "vector": [round(x, 6) for x in p.vector], "payload": p.payload},
                            ensure_ascii=False) for p in sorted(points, key=lambda p: str(p.id))]
        (config.INDEX_EXPORT_DIR / f"{coll}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"exported {len(lines)} points to corpus/index/{coll}.jsonl")


if __name__ == "__main__":
    build()