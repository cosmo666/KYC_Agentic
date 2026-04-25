from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator as orch
from app.db import models as m
from app.db.session import get_db
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatMessage, ChatResponse, ContactRequest, Widget

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


@router.post("/init", response_model=ChatResponse)
async def init_session(
    request: Request, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    """Bootstrap a fresh session — agent-initiated.

    Creates the sessions row, runs the graph through `n_greet` so it lands at
    `wait_for_contact`, generates the assistant's opening message + contact
    form widget, and returns it. The FE calls this on mount when no
    sessionId is in storage, so the user never has to type "hi" first.
    """
    sess_uuid = uuid.uuid4()
    sess = m.Session(id=sess_uuid, language="en", status="active")
    db.add(sess)
    await db.flush()
    session_id = str(sess_uuid)

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}
        new_state = await graph.ainvoke(
            {
                "session_id": session_id,
                "messages": [],
                "language": "en",
            },
            config=thread,
        )

        new_nr = new_state.get("next_required", "wait_for_contact")
        reply = await orch.generate_assistant_reply(
            request.app.state.ollama, new_state.get("language", "en"), new_nr
        )
        widget = orch.widget_for(new_nr, new_state)
        assistant_msg: dict = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget

        await graph.aupdate_state(thread, {"messages": [assistant_msg]})

        db.add(
            m.Message(
                session_id=sess_uuid,
                seq=0,
                role="assistant",
                content=reply,
                widget=widget,
            )
        )
        await db.commit()

    return ChatResponse(
        session_id=session_id,
        messages=[
            ChatMessage(
                role="assistant",
                content=reply,
                widget=Widget(**widget) if widget else None,
            )
        ],
        next_required=new_nr,
        language="en",
    )


@router.post("/contact", response_model=ChatResponse)
async def submit_contact(
    req: ContactRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    """Handle the contact_form widget submission. Persists email + mobile to
    the sessions row, advances the graph from wait_for_contact → wait_for_name,
    and returns the next assistant message (asking for the user's name).
    """
    sess_uuid = uuid.UUID(req.session_id)
    sess = await db.get(m.Session, sess_uuid)
    if sess is None:
        raise HTTPException(404, "Unknown session")

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": req.session_id}}
        snap = await graph.aget_state(thread)
        current = dict(snap.values) if snap and snap.values else {}

        if current.get("next_required") != "wait_for_contact":
            raise HTTPException(
                409,
                f"Session is not waiting for contact. "
                f"Current step: {current.get('next_required')}",
            )

        # Advance the checkpoint with the captured contact + the new wait state.
        await graph.aupdate_state(
            thread,
            {
                "session_id": req.session_id,
                "email": req.email,
                "mobile": req.mobile,
                "next_required": "wait_for_name",
            },
        )
        new_state = (await graph.aget_state(thread)).values

        # Persist to the sessions row.
        sess.email = req.email
        sess.mobile = req.mobile

        # Generate the next assistant message (asks for the user's name).
        language = current.get("language", "en")
        reply = (
            await orch.generate_assistant_reply(
                request.app.state.ollama, language, "wait_for_name"
            )
        ).strip()
        widget = orch.widget_for("wait_for_name", new_state)
        assistant_msg: dict = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget

        await graph.aupdate_state(thread, {"messages": [assistant_msg]})

        # Append to the messages table.
        seq = (
            await db.scalar(
                select(func.count())
                .select_from(m.Message)
                .where(m.Message.session_id == sess_uuid)
            )
        ) or 0
        db.add(
            m.Message(
                session_id=sess_uuid,
                seq=seq,
                role="assistant",
                content=reply,
                widget=widget,
            )
        )
        await db.commit()

    return ChatResponse(
        session_id=req.session_id,
        messages=[
            ChatMessage(
                role="assistant",
                content=reply,
                widget=Widget(**widget) if widget else None,
            )
        ],
        next_required="wait_for_name",
        language=language,
    )
