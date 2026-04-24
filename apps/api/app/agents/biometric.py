from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.graph.state import KYCState
from app.services.deepface_runner import analyze_gender, verify_faces


def _normalize_gender(s: str | None) -> str | None:
    if not s:
        return None
    t = s.strip().lower()
    if t.startswith("m"):
        return "man"
    if t.startswith("f") or t.startswith("w"):
        return "woman"
    return t


async def run_biometric(state: KYCState, db: AsyncSession) -> dict:
    """Verify selfie vs Aadhaar reference, analyse gender, persist, return delta."""
    selfie_slot = state.get("selfie", {})
    selfie_path = selfie_slot.get("file_path")
    aadhaar_slot = state.get("aadhaar", {})
    # Reference face: cropped Aadhaar photo if available, else the full Aadhaar image.
    reference = aadhaar_slot.get("photo_path") or aadhaar_slot.get("file_path")

    if not selfie_path or not reference:
        return {"next_required": "wait_for_selfie"}

    # DeepFace is sync + CPU-bound; run off the event loop.
    verify_res = await asyncio.to_thread(verify_faces, selfie_path, reference)

    aadhaar_fields = (
        aadhaar_slot.get("confirmed_json")
        or aadhaar_slot.get("extracted_json")
        or {}
    )
    aadhaar_gender = _normalize_gender(aadhaar_fields.get("gender"))
    if verify_res.get("faces_detected"):
        gender_res = await asyncio.to_thread(analyze_gender, selfie_path)
    else:
        gender_res = {"predicted_gender": None}
    predicted = gender_res.get("predicted_gender")
    gender_match = None
    if aadhaar_gender and predicted:
        gender_match = aadhaar_gender == predicted

    # Persist selfie + face_check rows.
    session_uuid = uuid.UUID(state["session_id"])
    selfie_row = m.Selfie(session_id=session_uuid, file_path=selfie_path)
    db.add(selfie_row)
    await db.flush()

    await db.execute(
        pg_insert(m.FaceCheck)
        .values(
            session_id=session_uuid,
            selfie_id=selfie_row.id,
            verified=bool(verify_res["verified"]),
            distance=float(verify_res["distance"]),
            confidence=float(verify_res["confidence"]),
            predicted_gender=predicted,
            aadhaar_gender=aadhaar_gender,
            gender_match=gender_match,
            model="VGG-Face",
        )
        .on_conflict_do_update(
            index_elements=["session_id", "selfie_id"],
            set_={
                "verified": bool(verify_res["verified"]),
                "distance": float(verify_res["distance"]),
                "confidence": float(verify_res["confidence"]),
                "predicted_gender": predicted,
                "aadhaar_gender": aadhaar_gender,
                "gender_match": gender_match,
            },
        )
    )
    await db.commit()

    face_check = {
        "verified": verify_res["verified"],
        "confidence": verify_res["confidence"],
        "faces_detected": verify_res.get("faces_detected", True),
        "predicted_gender": predicted,
        "aadhaar_gender": aadhaar_gender,
        "gender_match": gender_match,
    }
    selfie_delta = {"file_path": selfie_path, "id": str(selfie_row.id)}

    flags = list(state.get("flags") or [])
    if not verify_res.get("faces_detected"):
        # Send the user back to retake the selfie.
        return {
            "face_check": face_check,
            "selfie": selfie_delta,
            "next_required": "wait_for_selfie",
        }
    if gender_match is False:
        flags.append("gender_mismatch")
    if verify_res["confidence"] < 60 and not verify_res["verified"]:
        flags.append("face_verification_low_confidence")

    return {
        "face_check": face_check,
        "selfie": selfie_delta,
        "flags": flags,
        "next_required": "geolocation",
    }
