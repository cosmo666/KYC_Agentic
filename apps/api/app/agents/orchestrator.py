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

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_DIGITS_RE = re.compile(r"\D+")
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def extract_email(text: str) -> str | None:
    """Pull an email out of free-text user input. Returns lowercased email
    or None if no valid email is present."""
    if not text:
        return None
    candidate = text.strip().lower()
    if _EMAIL_RE.match(candidate):
        return candidate
    # Scan token-by-token in case the user wrote a sentence around the email.
    for token in re.split(r"\s+", text):
        token = token.strip(".,;:!?()<>").lower()
        if _EMAIL_RE.match(token):
            return token
    return None


def extract_indian_mobile(text: str) -> str | None:
    """Pull a 10-digit Indian mobile out of free-text. Strips +91/91/0
    prefixes, spaces, dashes. Returns the 10-digit local number or None."""
    if not text:
        return None
    digits = _DIGITS_RE.sub("", text)
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if _INDIAN_MOBILE_RE.match(digits):
        return digits
    return None


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


_INTENT_PROMPT = """Classify the user's latest message in a KYC chat as exactly one of:
- continue_flow: answering the current step
- faq: general KYC / compliance / privacy question
- clarify: asking about the CURRENT step itself

Respond JSON: {"intent": "..."}
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

_REPLY_PROMPT = """You are a warm, concise KYC assistant for Indian users.
Reply in {lang} (en=English, hi=Devanagari, mixed=Hinglish).

Task: {instruction}

Rules: 1-2 short sentences, one question max, no internal step names.
"""


# next_required → (english instruction for LLM, static widget envelope)
STEP_WIDGETS: dict[str, tuple[str, dict | None]] = {
    "wait_for_contact": (
        "Greet warmly in one sentence, then point to the form below in another. "
        "Don't name fields. No markdown. Max 25 words.",
        None,  # widget filled at runtime in widget_for()
    ),
    "wait_for_name": (
        "Thank them. Now ask for their full name as it appears on their "
        "government-issued ID.",
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
    "done": (
        "Announce the verdict from Extra context in ONE sentence (max 25 words). "
        "Don't ask the user anything. "
        "approved → congratulate. flagged → say a human will review. "
        "rejected → state the reason briefly.",
        None,
    ),
}


async def generate_assistant_reply(
    ollama: OllamaClient,
    language: str,
    next_required: str,
    extra_context: str = "",
    state: dict | None = None,
) -> str:
    instruction = STEP_WIDGETS.get(next_required, ("Continue the conversation.", None))[0]
    # Auto-inject decision context for the terminal "done" step. Without this
    # the LLM doesn't know the actual verdict and ends up asking the user
    # to provide it ("Just paste the verdict here…").
    if next_required == "done" and state is not None:
        decision = state.get("decision") or "pending"
        reason = state.get("decision_reason") or ""
        verdict_ctx = f"Decision: {decision}. Reason: {reason}".strip()
        extra_context = (
            f"{verdict_ctx}\n\n{extra_context}".strip()
            if extra_context
            else verdict_ctx
        )
    if extra_context:
        instruction = f"{instruction}\n\nExtra context: {extra_context}"
    raw = await ollama.chat(
        [
            {
                "role": "system",
                "content": _REPLY_PROMPT.format(lang=language, instruction=instruction),
            },
            {"role": "user", "content": "Generate the reply now."},
        ],
        temperature=0.5,
    )
    # Models often append trailing newlines / blank lines; strip so chat
    # bubbles don't render with empty whitespace at the bottom.
    return raw.strip()


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
    if widget is None:
        if next_required == "wait_for_contact":
            return {
                "type": "contact_form",
                "fields": [
                    {
                        "name": "email",
                        "label": "Email address",
                        "value": (state or {}).get("email", "") or "",
                        "placeholder": "you@example.com",
                        "input_type": "email",
                    },
                    {
                        "name": "mobile",
                        "label": "Mobile number",
                        "value": (state or {}).get("mobile", "") or "",
                        "placeholder": "98765 43210",
                        "input_type": "tel",
                    },
                ],
            }
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
            # Convert /data/uploads/<sid>/<file> filesystem paths into URLs the
            # FE can fetch via the /uploads/{sid}/{file} route. Returning
            # relative URLs lets the FE prepend its own API base.
            def _to_url(p: str | None) -> str | None:
                if not p:
                    return None
                if p.startswith("/data/uploads/"):
                    return p.replace("/data", "", 1)
                return None

            selfie_url = _to_url((state.get("selfie") or {}).get("file_path"))
            aadhaar_face_url = _to_url(
                (state.get("aadhaar") or {}).get("photo_path")
            )

            return {
                "type": "verdict",
                "decision": state.get("decision", "pending"),
                "decision_reason": state.get("decision_reason", ""),
                "checks": state.get("cross_validation", {}).get("checks", []),
                "flags": state.get("flags", []),
                "recommendations": state.get("recommendations", []),
                # Surface every per-check payload so the verdict card can
                # render distinct sections for face / gender / location and
                # the user can SEE which checks ran and what each said.
                "face_check": state.get("face_check", {}),
                "ip_check": state.get("ip_check", {}),
                # Image URLs for the side-by-side face comparison visual.
                "selfie_url": selfie_url,
                "aadhaar_face_url": aadhaar_face_url,
            }
    return widget
