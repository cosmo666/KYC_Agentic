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
from app.utils import get_client_ip

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


@router.post("", response_model=ChatResponse)
async def upload(
    request: Request,
    session_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")
    if doc_type not in ("aadhaar", "pan"):
        raise HTTPException(400, f"Unknown doc_type: {doc_type}")

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}
        snap = await graph.aget_state(thread)
        current = dict(snap.values) if snap and snap.values else {}

        expected = {
            "aadhaar": "wait_for_aadhaar_image",
            "pan": "wait_for_pan_image",
        }[doc_type]
        if current.get("next_required") != expected:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Not ready for {doc_type} yet. "
                    f"Current step: {current.get('next_required')}"
                ),
            )

        # Save file under /data/uploads/<session>/<doc>.<ext>
        s = get_settings()
        upload_dir = Path(s.upload_dir) / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix or ".bin"
        dest = upload_dir / f"{doc_type}{suffix}"
        dest.write_bytes(await file.read())

        # Delta input: set the file_path slot and flip to the ocr step.
        # The checkpoint already holds messages + prior fields.
        delta = {
            "session_id": session_id,
            doc_type: {**current.get(doc_type, {}), "file_path": str(dest)},
            "next_required": f"ocr_{doc_type}",
            "_client_ip": get_client_ip(request),
        }
        try:
            new_state = await graph.ainvoke(delta, config=thread)
        except Exception as exc:
            # OCR / vision-model / parser failure. Don't crash the user's
            # session — push the graph back to wait_for_<doc>_image so the
            # FE can re-render the upload widget and let them retry.
            print(f"[upload] {doc_type} intake failed: {exc!r}", flush=True)
            recovery = {
                "next_required": f"wait_for_{doc_type}_image",
                "flags": [
                    *(current.get("flags") or []),
                    f"{doc_type}_ocr_error",
                ],
            }
            await graph.aupdate_state(thread, recovery)
            new_state = (await graph.aget_state(thread)).values

        new_nr = new_state["next_required"]
        language = current.get("language", "en")
        reply = await orch.generate_assistant_reply(
            request.app.state.ollama, language, new_nr, state=new_state
        )
        widget = orch.widget_for(new_nr, new_state)
        assistant_msg: dict = {"role": "assistant", "content": reply}
        if widget:
            assistant_msg["widget"] = widget

        await graph.aupdate_state(thread, {"messages": [assistant_msg]})

        # Persist the assistant row to the domain table.
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
