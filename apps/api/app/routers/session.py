from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.db.session import get_db
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatMessage, ChatResponse, Widget

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/{session_id}", response_model=ChatResponse)
async def get_session(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    sess = await db.get(m.Session, uuid.UUID(session_id))
    if sess is None:
        raise HTTPException(404, "Unknown session")

    msgs_q = await db.execute(
        select(m.Message)
        .where(m.Message.session_id == sess.id)
        .order_by(m.Message.seq)
    )
    msgs = list(msgs_q.scalars().all())

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        snap = await graph.aget_state({"configurable": {"thread_id": session_id}})
        next_required = (
            (snap.values or {}).get("next_required") if snap else "done"
        ) or "done"

    return ChatResponse(
        session_id=session_id,
        messages=[
            ChatMessage(
                role=mm.role,
                content=mm.content,
                widget=Widget(**mm.widget) if mm.widget else None,
            )
            for mm in msgs
        ],
        next_required=next_required,
        language=sess.language or "en",
    )
