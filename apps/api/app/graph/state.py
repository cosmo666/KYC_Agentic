from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

NextRequired = Literal[
    "greet",
    "ask_name",
    "wait_for_name",
    "ask_aadhaar",
    "wait_for_aadhaar_image",
    "ocr_aadhaar",
    "confirm_aadhaar",
    "wait_for_aadhaar_confirm",
    "ask_pan",
    "wait_for_pan_image",
    "ocr_pan",
    "confirm_pan",
    "wait_for_pan_confirm",
    "cross_validate",
    "ask_selfie",
    "wait_for_selfie",
    "biometric",
    "geolocation",
    "decide",
    "done",
]

Decision = Literal["pending", "approved", "flagged", "rejected"]


class KYCState(TypedDict, total=False):
    session_id: str
    language: str  # "en" | "hi" | "mixed"
    user_name: str | None

    aadhaar: dict  # {file_path, extracted_json, confirmed_json, photo_path, ocr_confidence}
    pan: dict
    selfie: dict  # {file_path, id}

    cross_validation: dict  # {overall_score, checks[]}
    face_check: dict  # {verified, confidence, gender_match}
    ip_check: dict  # {country_ok, city_match, state_match, ip, city, region}

    messages: Annotated[list, add_messages]

    next_required: NextRequired
    decision: Decision
    decision_reason: str
    flags: list[str]
    recommendations: list[str]
