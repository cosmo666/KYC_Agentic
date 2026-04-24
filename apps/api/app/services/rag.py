from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.services.ollama_client import OllamaClient


class RAGService:
    def __init__(self, qdrant: AsyncQdrantClient, ollama: OllamaClient):
        self.q = qdrant
        self.ollama = ollama
        self.collection = get_settings().qdrant_collection

    async def ensure_collection(self, vector_size: int = 1024) -> None:
        cols = await self.q.get_collections()
        if any(c.name == self.collection for c in cols.collections):
            return
        await self.q.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    async def upsert_chunks(self, chunks: list[dict]) -> None:
        """chunks: [{id, text, source, metadata}]"""
        points: list[PointStruct] = []
        for ch in chunks:
            vec = await self.ollama.embed(ch["text"])
            points.append(
                PointStruct(
                    id=ch["id"],
                    vector=vec,
                    payload={
                        "text": ch["text"],
                        "source": ch["source"],
                        **ch.get("metadata", {}),
                    },
                )
            )
        await self.q.upsert(collection_name=self.collection, points=points)

    async def retrieve(self, query: str, k: int = 4) -> list[dict]:
        vec = await self.ollama.embed(query)
        res = await self.q.query_points(
            collection_name=self.collection, query=vec, limit=k, with_payload=True
        )
        return [
            {"text": h.payload["text"], "source": h.payload["source"], "score": h.score}
            for h in res.points
        ]
