from __future__ import annotations

import json
import re
from typing import Literal

from app.graph.state import KYCState
from app.services.ollama_client import OllamaClient

Language = Literal["en", "hi", "mixed"]
Intent = Literal["continue_flow", "faq", "clarify"]


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_HINGLISH_HINTS = re.compile(
    r"\b(hai|haan|nahi|naam|mera|aap|theek|karo|kya|kyu|kyun|kaise|kaisa)\b",
    re.I,
)


def detect_language(text: str) -> Language:
    """Cheap, deterministic language detection for the first turn.

    - Any Devanagari → hi
    - Latin script with common Hinglish tokens → mixed
    - Otherwise → en
    """
    if _DEVANAGARI.search(text):
        return "hi"
    if _HINGLISH_HINTS.search(text):
        return "mixed"
    return "en"


def heuristic_intent(text: str) -> Intent:
    """Fallback for when the LLM is unavailable, and a fast-path.

    Ends with `?` or starts with a wh-word → faq.
    Otherwise → continue_flow (the LLM can override).
    """
    t = text.strip().lower()
    if t.endswith("?") or t.startswith(
        (
            "what ",
            "why ",
            "how ",
            "when ",
            "who ",
            "where ",
            "can i",
            "is it",
        )
    ):
        return "faq"
    return "continue_flow"


_INTENT_PROMPT = """You are the intent classifier for a KYC chat assistant. The user is mid-flow completing KYC.

Classify the latest user message as exactly one of:
- "continue_flow" — user is answering the current step (name, confirming a value, etc.)
- "faq" — user is asking a general question about KYC, compliance, the process, data privacy
- "clarify" — user is asking about the CURRENT step specifically ("what should I upload?", "why do you need this?")

Respond with JSON: {"intent": "<one of the three>"}
"""


async def classify_intent(
    ollama: OllamaClient, user_text: str, current_step: str
) -> Intent:
    """LLM-driven intent classification. Falls back to heuristic on any error."""
    try:
        raw = await ollama.chat(
            [
                {"role": "system", "content": _INTENT_PROMPT},
                {
                    "role": "user",
                    "content": f"Current step: {current_step}\nUser said: {user_text}",
                },
            ],
            json_mode=True,
            temperature=0.0,
        )
        data = json.loads(raw)
        intent = data.get("intent", "continue_flow")
        if intent in ("continue_flow", "faq", "clarify"):
            return intent
    except Exception:
        pass
    return heuristic_intent(user_text)


def update_language(state: KYCState, user_text: str) -> Language:
    """Track consecutive-turn language switching.

    A single outlier turn is ignored; only after 2 consecutive turns in a new
    language do we switch. See spec §6.4.
    """
    current = state.get("language") or detect_language(user_text)
    detected = detect_language(user_text)
    if detected == current:
        state["language"] = current
        state["_lang_streak"] = 0
        return current
    streak = state.get("_lang_streak", 0) + 1
    if streak >= 2:
        state["language"] = detected
        state["_lang_streak"] = 0
        return detected
    state["_lang_streak"] = streak
    return current
