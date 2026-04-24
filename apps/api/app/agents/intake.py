from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.ollama_client import OllamaClient, strip_json_fence

AADHAAR_PROMPT = """You are extracting fields from an Indian Aadhaar card.

Return ONLY a JSON object with these keys — empty string if absent:
{
  "doc_type": "aadhaar",
  "name": "",
  "dob": "DD/MM/YYYY",
  "gender": "Male" | "Female" | "Other" | "",
  "aadhaar_number": "XXXX XXXX NNNN",
  "address": ""
}

Rules:
- The Aadhaar number MUST be masked: replace the first 8 digits with X. Keep the last 4 visible.
- Never return the full unmasked Aadhaar number.
- Normalise the DOB to DD/MM/YYYY.
- If the image is not an Aadhaar card, return the keys with empty strings.
"""

PAN_PROMPT = """You are extracting fields from an Indian PAN card.

Return ONLY a JSON object with these keys — empty string if absent:
{
  "doc_type": "pan",
  "name": "",
  "dob": "DD/MM/YYYY",
  "pan_number": "AAAAA9999A",
  "father_name": ""
}

Rules:
- PAN number is 10 characters: 5 letters, 4 digits, 1 letter.
- Normalise the DOB to DD/MM/YYYY.
- If the image is not a PAN card, return the keys with empty strings.
"""


def mask_aadhaar(value: str) -> str:
    """Leave only the last 4 digits visible.

    Accept '1234 5678 9012', '123456789012', or already-masked input.
    """
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) != 12:
        if re.fullmatch(r"(X{4} ){2}\d{4}", value.strip()):
            return value.strip()
        return value
    return f"XXXX XXXX {digits[-4:]}"


def parse_vision_output(raw: str) -> dict:
    """Accept raw model output (optionally fenced) and return a dict."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return strip_json_fence(raw)


def pick_ocr_confidence(fields: dict) -> str:
    """Cheap quality heuristic on the extracted fields."""
    if not fields.get("name"):
        return "low"
    required = ["name", "dob"]
    doc_type = fields.get("doc_type")
    if doc_type == "aadhaar":
        required += ["aadhaar_number"]
    elif doc_type == "pan":
        required += ["pan_number"]
    missing = sum(1 for k in required if not fields.get(k))
    if missing == 0:
        extras_present = (
            doc_type != "aadhaar"
            or (fields.get("gender") and fields.get("address"))
        )
        if extras_present:
            return "high"
    return "medium" if missing <= 1 else "low"


async def extract_fields(
    ollama: OllamaClient, image_path: str | Path, doc_type: str
) -> tuple[dict, str]:
    """Run vision OCR; return (fields_dict, confidence)."""
    prompt = AADHAAR_PROMPT if doc_type == "aadhaar" else PAN_PROMPT
    raw = await ollama.vision_extract(prompt, image_path)
    fields = parse_vision_output(raw)
    fields["doc_type"] = doc_type  # enforce
    if doc_type == "aadhaar" and fields.get("aadhaar_number"):
        fields["aadhaar_number"] = mask_aadhaar(fields["aadhaar_number"])
    return fields, pick_ocr_confidence(fields)


# ───────────────────────── graph node entry point ─────────────────────────

import uuid  # noqa: E402

from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db import models as _dbm  # noqa: E402
from app.graph.state import KYCState  # noqa: E402


async def run_intake(
    state: KYCState,
    db: AsyncSession,
    ollama: OllamaClient,
    doc_type: str,
) -> dict:
    """Run OCR, persist to `documents`, return the state delta.

    Precondition: state[doc_type]["file_path"] must be set by /upload.
    """
    slot = dict(state.get(doc_type, {}))
    file_path = slot.get("file_path")
    if not file_path:
        return {}

    fields, confidence = await extract_fields(ollama, file_path, doc_type)
    slot["extracted_json"] = fields
    slot["ocr_confidence"] = confidence

    session_id = uuid.UUID(state["session_id"])
    stmt = pg_insert(_dbm.Document).values(
        session_id=session_id,
        doc_type=doc_type,
        file_path=file_path,
        extracted_json=fields,
        ocr_confidence=confidence,
        engine="ollama_vision",
    ).on_conflict_do_update(
        index_elements=["session_id", "doc_type"],
        set_={
            "file_path": file_path,
            "extracted_json": fields,
            "ocr_confidence": confidence,
            "engine": "ollama_vision",
        },
    )
    await db.execute(stmt)
    await db.commit()

    delta: dict = {doc_type: slot}
    if confidence == "low":
        # Send the user back to re-upload.
        delta["next_required"] = f"wait_for_{doc_type}_image"
        delta["flags"] = [
            *(state.get("flags") or []),
            f"{doc_type}_ocr_low_confidence",
        ]
    else:
        delta["next_required"] = f"wait_for_{doc_type}_confirm"
    return delta
