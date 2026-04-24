from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator as orch
from app.config import get_settings
from app.db import models as m
from app.db.session import get_db
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatMessage, ChatResponse, Widget

router = APIRouter(prefix="/capture", tags=["capture"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
EXPECTED = {
    "selfie": "wait_for_selfie",
    "aadhaar": "wait_for_aadhaar_image",
    "pan": "wait_for_pan_image",
}


@router.post("", response_model=ChatResponse)
async def capture(
    request: Request,
    session_id: str = Form(...),
    target: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if target not in EXPECTED:
        raise HTTPException(400, f"Unknown target: {target}")
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}
        snap = await graph.aget_state(thread)
        current = dict(snap.values) if snap and snap.values else {}

        if current.get("next_required") != EXPECTED[target]:
            raise HTTPException(
                409,
                f"Not ready for {target}. Current step: {current.get('next_required')}",
            )

        s = get_settings()
        upload_dir = Path(s.upload_dir) / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix or ".jpg"
        dest = upload_dir / f"{target}{suffix}"
        dest.write_bytes(await file.read())

        if target == "selfie":
            delta = {
                "session_id": session_id,
                "selfie": {"file_path": str(dest)},
                "next_required": "biometric",
            }
        else:
            delta = {
                "session_id": session_id,
                target: {
                    **current.get(target, {}),
                    "file_path": str(dest),
                },
                "next_required": f"ocr_{target}",
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

        sess_uuid = uuid.UUID(session_id)
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
        session_id=session_id,
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
