from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import BaseMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qdrant_client import AsyncQdrantClient

from app.agents import orchestrator as orch
from app.agents.compliance import answer_faq, persist_compliance_qna
from app.config import get_settings
from app.db import models as m
from app.db.session import get_db
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, Widget
from app.services.rag import RAGService
from app.utils import get_client_ip

router = APIRouter(prefix="/chat", tags=["chat"])


def _msg_to_dict(msg) -> dict:
    """Normalise dict / BaseMessage into the persistence shape."""
    if isinstance(msg, BaseMessage):
        role = {"human": "user", "ai": "assistant", "system": "system"}.get(
            msg.type, msg.type
        )
        return {"role": role, "content": msg.content}
    return {"role": msg["role"], "content": msg["content"], "widget": msg.get("widget")}


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    ollama = request.app.state.ollama
    session_id = req.session_id or str(uuid.uuid4())
    session_uuid = uuid.UUID(session_id)

    # Ensure a sessions row exists for this thread.
    sess = await db.get(m.Session, session_uuid)
    if sess is None:
        sess = m.Session(id=session_uuid, language="en", status="active")
        db.add(sess)
        await db.flush()

    user_msg_dict = {"role": "user", "content": req.text}

    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": session_id}}

        snap = await graph.aget_state(thread)
        has_prior_state = bool(snap and snap.values)

        # Language tracking uses a shallow copy of prior state so we don't
        # push partial dict updates through add_messages.
        prior = dict(snap.values) if has_prior_state else {}
        language = orch.update_language(prior, req.text)
        sess.language = language

        # Build the ainvoke input — on first turn we need seed fields;
        # on continuation we pass only the deltas.
        ainvoke_input: dict = {
            "messages": [user_msg_dict],
            "language": language,
            "_client_ip": get_client_ip(request),
        }
        if not has_prior_state:
            ainvoke_input["session_id"] = session_id

        # Optional intent classification (only mid-flow).
        nr_before = prior.get("next_required")
        intent = "continue_flow"
        if nr_before and nr_before != "greet":
            intent = await orch.classify_intent(ollama, req.text, nr_before)

        if intent == "faq":
            qdrant = AsyncQdrantClient(url=get_settings().qdrant_url)
            try:
                rag = RAGService(qdrant, ollama)
                answer, sources = await answer_faq(rag, ollama, req.text, language)
            finally:
                await qdrant.close()
            await persist_compliance_qna(db, session_id, req.text, answer, sources)
            await graph.aupdate_state(
                thread,
                {
                    "messages": [
                        user_msg_dict,
                        {"role": "assistant", "content": answer},
                    ],
                    "language": language,
                },
            )
            new_state_values = (await graph.aget_state(thread)).values
            assistant_msg = {"role": "assistant", "content": answer}
            widget = None
        elif intent == "clarify":
            clarification = await ollama.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            f"KYC assistant. Clarify the current step ({nr_before}) "
                            f"to the user. Reply in {language}. 1-2 sentences."
                        ),
                    },
                    {"role": "user", "content": req.text},
                ],
                temperature=0.3,
            )
            await graph.aupdate_state(
                thread,
                {
                    "messages": [
                        user_msg_dict,
                        {"role": "assistant", "content": clarification},
                    ],
                    "language": language,
                },
            )
            new_state_values = (await graph.aget_state(thread)).values
            assistant_msg = {"role": "assistant", "content": clarification}
            widget = None
        else:
            # Special case: at wait_for_contact, the contact_form widget is the
            # ONLY way to advance — typed messages don't auto-extract. Reply
            # politely pointing back to the form rather than running the graph.
            if nr_before == "wait_for_contact":
                reply_text = (
                    "Please share your email and mobile using the form above to begin."
                )
                widget = None
                assistant_msg = {"role": "assistant", "content": reply_text}
                await graph.aupdate_state(
                    thread,
                    {
                        "messages": [user_msg_dict, assistant_msg],
                        "language": language,
                    },
                )
                new_state_values = (await graph.aget_state(thread)).values
            else:
                # Run the graph one step — its entry conditional routes on next_required.
                new_state_values = await graph.ainvoke(ainvoke_input, config=thread)

                new_nr = new_state_values.get("next_required", "done")
                hint = new_state_values.get("_validation_hint", "")
                reply_text = (
                    await orch.generate_assistant_reply(
                        ollama,
                        language,
                        new_nr,
                        extra_context=hint,
                        state=new_state_values,
                    )
                ).strip()  # LLMs sometimes append trailing newlines.
                widget = orch.widget_for(new_nr, new_state_values)
                assistant_msg = {"role": "assistant", "content": reply_text}
                if widget:
                    assistant_msg["widget"] = widget

                updates: dict = {"messages": [assistant_msg]}
                if hint:
                    updates["_validation_hint"] = ""
                await graph.aupdate_state(thread, updates)

                # Persist newly-captured email / mobile to the sessions row.
                new_email = new_state_values.get("email")
                new_mobile = new_state_values.get("mobile")
                if new_email and sess.email != new_email:
                    sess.email = new_email
                if new_mobile and sess.mobile != new_mobile:
                    sess.mobile = new_mobile

        # Persist messages to the domain table, skipping rows we've already written.
        existing_count = (
            await db.scalar(
                select(func.count())
                .select_from(m.Message)
                .where(m.Message.session_id == session_uuid)
            )
        ) or 0
        all_msgs = (await graph.aget_state(thread)).values.get("messages", [])
        normalized = [_msg_to_dict(x) for x in all_msgs]
        for seq, msg in enumerate(normalized[existing_count:], start=existing_count):
            db.add(
                m.Message(
                    session_id=session_uuid,
                    seq=seq,
                    role=msg["role"],
                    content=msg["content"],
                    widget=msg.get("widget"),
                )
            )
        await db.commit()

    # Response carries only the latest user + assistant turn.
    response_msgs: list[ChatMessage] = [ChatMessage(role="user", content=req.text)]
    response_msgs.append(
        ChatMessage(
            role="assistant",
            content=assistant_msg["content"],
            widget=Widget(**widget) if widget else None,
        )
    )
    return ChatResponse(
        session_id=session_id,
        messages=response_msgs,
        next_required=new_state_values.get("next_required", "done"),
        language=language,
    )
