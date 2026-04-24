# backend/models/chat_schemas.py

from pydantic import BaseModel
from typing import List, Optional, Union


class ChatMessage(BaseModel):
    role: str       # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    document_context: Optional[Union[List[dict], dict]] = None


class ChatResponse(BaseModel):
    reply: str
    suggestions: List[str] = []
