from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from app.rag import config

model = SentenceTransformer(config.EMBEDDING_MODEL)
dim = model.get_embedding_dimension()
print("model OK, dim =", dim, "| max_seq_length =", model.max_seq_length)

client = QdrantClient(path=config.QDRANT_PATH)
client.recreate_collection("smoke", vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
docs = ["Phenoxyethanol max 1% in cosmetic products", "Glycerin is a humectant"]
vecs = model.encode(docs, normalize_embeddings=True)
client.upsert("smoke", [PointStruct(id=i, vector=v.tolist(), payload={"t": d})
                        for i, (v, d) in enumerate(zip(vecs, docs))])
q = model.encode(config.QUERY_PREFIX + "preservative concentration limit", normalize_embeddings=True)
hit = client.query_points("smoke", query=q.tolist(), limit=1).points[0]
print("retrieval OK ->", hit.payload["t"], round(hit.score, 3))
client.delete_collection("smoke")