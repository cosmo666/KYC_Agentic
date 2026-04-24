"""Index the RAG corpus into Qdrant.

Usage (inside the api container):
    uv run python -m app.scripts.reindex_rag
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.services.ollama_client import OllamaClient
from app.services.rag import RAGService

CORPUS_DIR = Path(os.environ.get("RAG_CORPUS_DIR", "/corpus"))


def _chunk(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking with a length cap and overlap for giant paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                for i in range(0, len(p), max_chars - overlap):
                    chunks.append(p[i : i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _id_for(source: str, idx: int, text: str) -> int:
    """Stable 63-bit int id (Qdrant accepts int or UUID)."""
    h = hashlib.sha1(f"{source}:{idx}:{text[:64]}".encode()).hexdigest()[:15]
    return int(h, 16)


async def main() -> None:
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=120) as http:
        ollama = OllamaClient(http, s.chat_model, s.ocr_model, s.embed_model)
        q = AsyncQdrantClient(url=s.qdrant_url)

        # Probe embed dimensionality with a tiny input.
        sample_vec = await ollama.embed("dimension probe")
        dim = len(sample_vec)
        print(f"[reindex] embedding dim = {dim}")

        rag = RAGService(q, ollama)
        rag.collection = s.qdrant_collection
        await rag.ensure_collection(vector_size=dim)

        paths = sorted(
            p
            for p in CORPUS_DIR.glob("**/*")
            if p.is_file() and p.suffix in {".md", ".txt"}
        )
        if not paths:
            print(f"[reindex] no files found under {CORPUS_DIR}")
            return

        total = 0
        for p in paths:
            text = p.read_text(encoding="utf-8")
            chunks = _chunk(text)
            print(f"[reindex] {p.name}: {len(chunks)} chunks")
            payloads = [
                {
                    "id": _id_for(p.name, idx, ch),
                    "text": ch,
                    "source": p.name,
                    "metadata": {"path": str(p.relative_to(CORPUS_DIR))},
                }
                for idx, ch in enumerate(chunks)
            ]
            # Batch to keep embed calls concurrent without overloading Ollama.
            for i in range(0, len(payloads), 16):
                await rag.upsert_chunks(payloads[i : i + 16])
            total += len(payloads)

        print(f"[reindex] upserted {total} chunks into '{s.qdrant_collection}'")
        await q.close()


if __name__ == "__main__":
    asyncio.run(main())
