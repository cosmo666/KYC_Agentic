from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.services.ollama_client import OllamaClient
from app.services.rag import RAGService

FAQ_PROMPT = """You are a KYC assistant. Use the CONTEXT below to answer the user's question.
- If the context doesn't contain the answer, say so plainly; don't invent facts.
- Reply in the user's language ({lang}).
- Keep it to 2-4 sentences.
- At the end, include a short "Sources:" line listing the source file names used.

CONTEXT:
{context}
"""


async def answer_faq(
    rag: RAGService,
    ollama: OllamaClient,
    question: str,
    language: str = "en",
) -> tuple[str, list[dict]]:
    hits = await rag.retrieve(question, k=4)
    if not hits:
        return (
            "I don't have that in my knowledge base yet. Could you rephrase or ask something else?",
            [],
        )
    context = "\n\n---\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
    answer = await ollama.chat(
        [
            {
                "role": "system",
                "content": FAQ_PROMPT.format(lang=language, context=context),
            },
            {"role": "user", "content": question},
        ],
        temperature=0.2,
    )
    sources = [{"source": h["source"], "score": h["score"]} for h in hits]
    return answer, sources


async def persist_compliance_qna(
    db: AsyncSession,
    session_id: str,
    question: str,
    answer: str,
    sources: list[dict],
) -> None:
    db.add(
        m.ComplianceQna(
            session_id=uuid.UUID(session_id),
            question=question,
            answer=answer,
            sources=sources,
        )
    )
    await db.commit()
