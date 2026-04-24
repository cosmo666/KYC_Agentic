from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator as orch
from app.agents.intake import mask_aadhaar
from app.db import models as m
from app.db.session import get_db
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatMessage, ChatResponse, Widget

router = APIRouter(prefix="/confirm", tags=["confirm"])


class ConfirmRequest(BaseModel):
    session_id: str
    doc_type: str
    fields: dict


@router.post("", response_model=ChatResponse)
async def confirm(
    req: ConfirmRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    if req.doc_type not in ("aadhaar", "pan"):
        raise HTTPException(400, "doc_type must be 'aadhaar' or 'pan'")

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": req.session_id}}
        snap = await graph.aget_state(thread)
        current = dict(snap.values) if snap and snap.values else {}

        expected = f"wait_for_{req.doc_type}_confirm"
        if current.get("next_required") != expected:
            raise HTTPException(
                409,
                f"Not ready to confirm {req.doc_type}. "
                f"Current step: {current.get('next_required')}",
            )

        # Re-mask Aadhaar if the user tried to un-mask during edit.
        confirmed = dict(req.fields)
        if req.doc_type == "aadhaar" and confirmed.get("aadhaar_number"):
            confirmed["aadhaar_number"] = mask_aadhaar(confirmed["aadhaar_number"])

        sess_uuid = uuid.UUID(req.session_id)
        await db.execute(
            update(m.Document)
            .where(
                m.Document.session_id == sess_uuid,
                m.Document.doc_type == req.doc_type,
            )
            .values(
                confirmed_json=confirmed,
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        # Advance the graph with a delta. aadhaar_confirm → wait_for_pan_image
        # halts at a wait state; pan_confirm → cross_validate runs through the
        # validation/biometric/geolocation/decide chain via the stubs (until
        # Phases 8-11 replace them).
        slot = {**current.get(req.doc_type, {}), "confirmed_json": confirmed}
        next_step = (
            "wait_for_pan_image" if req.doc_type == "aadhaar" else "cross_validate"
        )
        delta = {
            "session_id": req.session_id,
            req.doc_type: slot,
            "next_required": next_step,
        }
        new_state = await graph.ainvoke(delta, config=thread)

        new_nr = new_state["next_required"]
        language = current.get("language", "en")
        reply = await orch.generate_assistant_reply(
            request.app.state.ollama, language, new_nr
        )
        widget = orch.widget_for(new_nr, new_state)
        assistant_msg: dict = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget

        await graph.aupdate_state(thread, {"messages": [assistant_msg]})

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
        next_required=new_nr,
        language=language,
    )
