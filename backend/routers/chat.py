# backend/routers/chat.py

from fastapi import APIRouter
from models.chat_schemas import ChatRequest, ChatResponse
from services.chat_service import get_chat_response

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the KYC Assistant chatbot.
    Supports conversation history and document context.
    """
    # Convert history to list of dicts
    history = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # Get Gemini response
    reply = get_chat_response(
        user_message=request.message,
        chat_history=history,
        document_context=request.document_context,
    )

    # Generate contextual suggestions
    suggestions = _get_suggestions(request.message, reply)

    return ChatResponse(reply=reply, suggestions=suggestions)


def _get_suggestions(user_msg: str, bot_reply: str) -> list:
    """Generate quick-reply suggestions based on context."""
    lower = user_msg.lower()

    if any(w in lower for w in ["hello", "hi", "hey", "start"]):
        return ["What is KYC?", "Start verification", "What documents do I need?"]
    elif any(w in lower for w in ["aadhaar", "aadhar"]):
        return ["Upload Aadhaar", "What if my Aadhaar is old?", "I don't have Aadhaar"]
    elif any(w in lower for w in ["pan", "pancard"]):
        return ["Upload PAN card", "How to get PAN?", "PAN vs Aadhaar"]
    elif any(w in lower for w in ["selfie", "photo", "face"]):
        return ["Take selfie", "Why do you need my photo?", "Camera not working"]
    elif any(w in lower for w in ["done", "complete", "finish", "submit"]):
        return ["Check my status", "Download report", "Start over"]
    else:
        return ["Upload document", "What is KYC?", "Help me"]
