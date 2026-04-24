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


# ─────────────────── reply generation + widget envelopes ───────────────────

_REPLY_PROMPT = """You are a warm, concise KYC assistant for Indian users. Reply in the user's language.

Language code: {lang}  (en=English, hi=Hindi in Devanagari, mixed=Hinglish in Latin script)

The workflow engine has decided the user must now do: {instruction}

Do NOT invent steps. Keep the reply to 1-2 short sentences. Never mention internal state names
(e.g. "next_required", "wait_for_aadhaar_image"). Do not ask more than one question at a time.
"""


# next_required → (english instruction for LLM, static widget envelope)
STEP_WIDGETS: dict[str, tuple[str, dict | None]] = {
    "wait_for_name": (
        "Ask the user for their full name.",
        None,
    ),
    "wait_for_aadhaar_image": (
        "Tell the user to upload a clear photo of their Aadhaar card (front). "
        "They can upload a file or use their camera.",
        {
            "type": "upload",
            "doc_type": "aadhaar",
            "accept": ["image/jpeg", "image/png", "application/pdf"],
        },
    ),
    "wait_for_aadhaar_confirm": (
        "Tell the user to review the fields we extracted from their Aadhaar and "
        "confirm or edit them.",
        None,  # widget filled at runtime with actual fields
    ),
    "wait_for_pan_image": (
        "Tell the user to upload a clear photo of their PAN card.",
        {
            "type": "upload",
            "doc_type": "pan",
            "accept": ["image/jpeg", "image/png", "application/pdf"],
        },
    ),
    "wait_for_pan_confirm": (
        "Tell the user to review the fields extracted from their PAN and confirm or edit them.",
        None,
    ),
    "wait_for_selfie": (
        "Tell the user to take a selfie for face verification.",
        {"type": "selfie_camera"},
    ),
    "done": ("Share the KYC verdict in plain language.", None),
}


async def generate_assistant_reply(
    ollama: OllamaClient,
    language: str,
    next_required: str,
    extra_context: str = "",
) -> str:
    instruction = STEP_WIDGETS.get(next_required, ("Continue the conversation.", None))[0]
    if extra_context:
        instruction = f"{instruction}\n\nExtra context: {extra_context}"
    return await ollama.chat(
        [
            {
                "role": "system",
                "content": _REPLY_PROMPT.format(lang=language, instruction=instruction),
            },
            {"role": "user", "content": "Generate the reply now."},
        ],
        temperature=0.5,
    )


_AADHAAR_FIELDS = [
    ("name", "Full name"),
    ("dob", "Date of birth"),
    ("gender", "Gender"),
    ("aadhaar_number", "Aadhaar number (masked)"),
    ("address", "Address"),
]
_PAN_FIELDS = [
    ("name", "Full name"),
    ("dob", "Date of birth"),
    ("pan_number", "PAN number"),
    ("father_name", "Father's name"),
]


def _fields_from_extracted(extracted: dict) -> list[dict]:
    doc_type = extracted.get("doc_type", "")
    fields = _AADHAAR_FIELDS if doc_type == "aadhaar" else _PAN_FIELDS
    return [
        {"name": k, "label": label, "value": extracted.get(k, "")} for k, label in fields
    ]


def widget_for(next_required: str, state: KYCState | None = None) -> dict | None:
    """Return the widget envelope for a given step, or None if not interactive."""
    widget = STEP_WIDGETS.get(next_required, (None, None))[1]
    if widget is None and state:
        if next_required == "wait_for_aadhaar_confirm":
            aadhaar = state.get("aadhaar", {})
            return {
                "type": "editable_card",
                "doc_type": "aadhaar",
                "fields": _fields_from_extracted(aadhaar.get("extracted_json", {})),
            }
        if next_required == "wait_for_pan_confirm":
            pan = state.get("pan", {})
            return {
                "type": "editable_card",
                "doc_type": "pan",
                "fields": _fields_from_extracted(pan.get("extracted_json", {})),
            }
        if next_required == "done":
            return {
                "type": "verdict",
                "decision": state.get("decision", "pending"),
                "decision_reason": state.get("decision_reason", ""),
                "checks": state.get("cross_validation", {}).get("checks", []),
                "flags": state.get("flags", []),
                "recommendations": state.get("recommendations", []),
            }
    return widget
