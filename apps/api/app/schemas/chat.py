from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WidgetType = Literal[
    "contact_form",
    "upload",
    "editable_card",
    "selfie_camera",
    "verdict",
]


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
    # IP-geolocation payload, attached on the verdict widget so the FE can
    # render the location card. Shape matches state["ip_check"]:
    # {ip, country_code, country_ok, city, region, city_match, state_match}
    ip_check: dict | None = None
    # Face + gender result from biometric. Shape matches state["face_check"]:
    # {verified, confidence, faces_detected, predicted_gender, aadhaar_gender,
    #  gender_match}
    face_check: dict | None = None
    # Relative URLs (prepend API base on FE) for the side-by-side face
    # comparison visual on the verdict card.
    selfie_url: str | None = None
    aadhaar_face_url: str | None = None


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


# ── Contact form (greet step) ────────────────────────────────────────
import re  # noqa: E402
from pydantic import field_validator  # noqa: E402

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_DIGITS_RE = re.compile(r"\D+")
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


class ContactRequest(BaseModel):
    session_id: str
    email: str = Field(min_length=3, max_length=254)
    mobile: str = Field(min_length=1, max_length=20)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("mobile")
    @classmethod
    def _check_mobile(cls, v: str) -> str:
        digits = _DIGITS_RE.sub("", v)
        # Drop a leading +91 / 91 / 0 so we end up with the 10-digit local number.
        if len(digits) > 10 and digits.startswith("91"):
            digits = digits[-10:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) != 10:
            raise ValueError(
                f"Mobile must be 10 digits (you entered {len(digits)})."
            )
        if not _INDIAN_MOBILE_RE.match(digits):
            raise ValueError(
                "Indian mobile must start with 6, 7, 8, or 9."
            )
        return digits


