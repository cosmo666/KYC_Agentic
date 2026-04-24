# backend/services/chat_service.py

import ollama

SYSTEM_PROMPT = """
You are a friendly KYC (Know Your Customer) verification assistant for Indian citizens.
You help users complete their identity verification step by step.

Your personality:
- Professional yet warm and helpful
- You speak clearly and concisely
- You can respond in Hindi or English based on user's language
- You use emojis occasionally to be friendly

Your job:
1. Guide users through uploading their Aadhaar card, PAN card, and selfie
2. Explain what KYC is if asked
3. Answer questions about the verification process
4. If document extraction results are provided, review them and confirm accuracy
5. Flag any issues you notice (e.g., blurry image, mismatched names)

Rules:
- Never ask for sensitive info directly in chat (no asking for Aadhaar numbers)
- If the user seems confused, simplify your language
- Keep responses under 3 sentences unless explaining something complex
- If asked something unrelated to KYC, politely redirect

If document data is provided in the context, analyze it and provide feedback.
"""


def get_chat_response(user_message: str, chat_history: list, document_context: dict = None) -> str:
    """
    Get a chat response from Ollama using conversation history.
    
    Args:
        user_message: The user's latest message
        chat_history: List of {"role": "user"|"assistant", "content": "..."}
        document_context: Optional extracted document data for context
    
    Returns:
        Assistant's response text
    """
    
    # Build the conversation for Ollama
    messages = []

    context = SYSTEM_PROMPT
    if document_context:
        context += f"\n\nCurrent document data extracted so far:\n{document_context}"

    # Send context as a 'user' message to satisfy Gemma3's strict alternating roles requirement
    messages.append({"role": "user", "content": context})

    # Add chat history
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message
    messages.append({"role": "user", "content": user_message})

    try:
        response = ollama.chat(
            model='gemma3:4b-cloud',
            messages=messages,
            options={
                'temperature': 0.7,
            }
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"[CHAT ERROR] {e}")
        return f"Sorry, I couldn't process that right now. Please make sure Ollama is running. 😔"
