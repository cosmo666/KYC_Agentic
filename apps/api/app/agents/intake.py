from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.ollama_client import OllamaClient, strip_json_fence

AADHAAR_PROMPT = """Extract fields from an Indian Aadhaar card. Return ONLY:
{"doc_type":"aadhaar","name":"","dob":"DD/MM/YYYY","gender":"Male|Female|Other","aadhaar_number":"NNNN NNNN NNNN","address":""}

- Aadhaar number: 12 digits in three groups of four. Return all 12 digits exactly as shown, left-to-right. Never mask.
- DOB: DD/MM/YYYY.
- Address: TRANSCRIBE EXACTLY as printed on the card, line by line, joined with commas. Do NOT invent, infer, complete, normalise, or substitute any place names, landmarks, PIN codes, or cities. If a character is unclear, copy what you see (e.g. "Leth" not "Leith"; "5/O" not "S/O"). If you cannot read part of the address, leave that part out — never replace it with a guess.
- Empty string for missing fields. If not an Aadhaar, all empty.
"""

PAN_PROMPT = """Extract fields from an Indian PAN card. Return ONLY:
{"doc_type":"pan","name":"","dob":"DD/MM/YYYY","pan_number":"AAAAA9999A","father_name":""}

PAN is 5 letters + 4 digits + 1 letter. DOB as DD/MM/YYYY. Empty string for missing fields. If not a PAN, all empty.
"""


def mask_aadhaar(value: str) -> str:
    """Leave only the last 4 digits visible. Always returns "XXXX XXXX NNNN".

    We never trust pre-masked input from the OCR model — vision LLMs sometimes
    grab the WRONG group of four when asked to mask, so the safe path is to
    re-derive the visible four from whichever digits we have. If we have:
      - exactly 12 digits → mask the first 8, keep the last 4 (the real case)
      - exactly 4 digits → assume they're the last group (already-masked input
        where the first 8 are already X-redacted)
      - anything else → return the input unchanged so the validator can flag it
    """
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12:
        return f"XXXX XXXX {digits[-4:]}"
    if len(digits) == 4 and re.fullmatch(r"(X{4} ){2}\d{4}", value.strip()):
        # Pre-masked by the model — trust the visible 4 only when the surrounding
        # structure clearly says "first two groups masked".
        return value.strip()
    return value


def parse_vision_output(raw: str) -> dict:
    """Accept raw model output (optionally fenced) and return a dict.

    `strict=False` lets json accept literal tabs / newlines inside string
    values — vision models routinely emit them in multi-line address fields.
    """
    try:
        return json.loads(raw, strict=False)
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


def render_pdf_first_page(pdf_path: str | Path, dpi: int = 200) -> Path | None:
    """Render the first page of a PDF to a sibling PNG and return its path.

    Returns None on failure (encrypted PDF, corrupt file, etc.) — callers
    should treat that as "could not OCR" and surface a friendly error.

    pymupdf is lazy-imported because it pulls in the bundled MuPDF binary
    (a few MB) and we only want to pay that cost when the user actually
    uploads a PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    src = Path(pdf_path)
    out = src.with_suffix(".png")
    try:
        with pymupdf.open(src) as doc:
            if doc.is_encrypted:
                print(f"[intake] PDF is encrypted, cannot render: {src.name}", flush=True)
                return None
            if len(doc) == 0:
                print(f"[intake] PDF has no pages: {src.name}", flush=True)
                return None
            pix = doc[0].get_pixmap(dpi=dpi)
            pix.save(out)
        print(
            f"[intake] rendered PDF first page -> {out.name} ({dpi} dpi)",
            flush=True,
        )
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[intake] PDF render failed for {src.name}: {exc!r}", flush=True)
        return None


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

    Also crops the holder's face out of the Aadhaar so the biometric agent
    can verify selfie ↔ photo (not selfie ↔ whole card). PAN photos are
    typically too low-res for reliable face match, so we skip cropping there
    — biometric will fall back to the full PAN if needed.

    Precondition: state[doc_type]["file_path"] must be set by /upload.
    """
    import asyncio

    from app.services.deepface_runner import extract_largest_face

    slot = dict(state.get(doc_type, {}))
    file_path = slot.get("file_path")
    if not file_path:
        return {}

    # PDFs aren't supported by the vision model directly. Render the first
    # page to PNG and use that for OCR + downstream face extraction. Keep
    # the original PDF on disk for audit, but switch the slot's file_path
    # to the rendered image so persistence + biometric agree.
    if Path(file_path).suffix.lower() == ".pdf":
        rendered = await asyncio.to_thread(render_pdf_first_page, file_path)
        if rendered is None:
            return {
                "next_required": f"wait_for_{doc_type}_image",
                "flags": [
                    *(state.get("flags") or []),
                    f"{doc_type}_pdf_render_failed",
                ],
                "_validation_hint": (
                    "The PDF could not be opened — it may be encrypted or "
                    "corrupted. Ask the user to upload a clear photo (JPG/PNG) "
                    "of the document instead."
                ),
            }
        slot["original_pdf_path"] = file_path
        slot["file_path"] = str(rendered)
        file_path = str(rendered)

    fields, confidence = await extract_fields(ollama, file_path, doc_type)
    slot["extracted_json"] = fields
    slot["ocr_confidence"] = confidence

    # Aadhaar only — crop the photo region. DeepFace.extract_faces is sync +
    # CPU-bound; run it off the event loop. Best-effort: if no face is found
    # the biometric agent still has the full image as a fallback.
    photo_path: str | None = None
    if doc_type == "aadhaar":
        photo_path = await asyncio.to_thread(extract_largest_face, file_path)
        if photo_path:
            slot["photo_path"] = photo_path
            print(f"[intake] aadhaar face cropped -> {photo_path}", flush=True)
        else:
            print(
                "[intake] aadhaar face crop FAILED — biometric will fall back "
                "to the full card image",
                flush=True,
            )

    session_id = uuid.UUID(state["session_id"])
    stmt = pg_insert(_dbm.Document).values(
        session_id=session_id,
        doc_type=doc_type,
        file_path=file_path,
        photo_path=photo_path,
        extracted_json=fields,
        ocr_confidence=confidence,
        engine="ollama_vision",
    ).on_conflict_do_update(
        index_elements=["session_id", "doc_type"],
        set_={
            "file_path": file_path,
            "photo_path": photo_path,
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
