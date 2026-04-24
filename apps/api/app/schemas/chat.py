from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WidgetType = Literal["upload", "editable_card", "selfie_camera", "verdict"]


class Widget(BaseModel):
    type: WidgetType
    # `upload`
    doc_type: str | None = None  # "aadhaar" | "pan"
    accept: list[str] | None = None  # mime types
    # `editable_card`
    fields: list[dict] | None = None  # [{name, label, value}]
    # `verdict`
    decision: str | None = None
    decision_reason: str | None = None
    checks: list[dict] | None = None
    flags: list[str] | None = None
    recommendations: list[str] | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    widget: Widget | None = None


class ChatRequest(BaseModel):
    session_id: str | None = None
    text: str = Field(min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    next_required: str
    language: str
