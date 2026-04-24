from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.graph.state import KYCState


def _critical_fails(checks: list[dict]) -> list[str]:
    fails: list[str] = []
    for c in checks or []:
        if c.get("status") == "fail" and c.get("name") in (
            "name_match",
            "dob_match",
        ):
            fails.append(f"{c['name']}_critical_fail")
    return fails


def compute_decision(state: KYCState) -> dict:
    """Pure, deterministic decision. See .claude/rules/agentic-workflow.md."""
    cv = state.get("cross_validation", {}) or {}
    score = float(cv.get("overall_score", 0))
    crit = _critical_fails(cv.get("checks", []))

    face = state.get("face_check", {}) or {}
    face_ok = bool(face.get("verified")) or float(face.get("confidence", 0)) >= 60
    faces_detected = face.get("faces_detected", True)

    ip = state.get("ip_check", {}) or {}
    country_ok = bool(ip.get("country_ok", True))

    # Dedup flags while preserving order.
    flags = list(dict.fromkeys([*(state.get("flags") or []), *crit]))

    if not country_ok:
        return {
            "decision": "rejected",
            "decision_reason": (
                "Your IP appears to be outside India. "
                "KYC for Indian residents requires an Indian IP."
            ),
            "flags": list(dict.fromkeys([*flags, "ip_country_not_india"])),
            "recommendations": [
                "Complete your KYC while connected from within India.",
            ],
        }
    if crit:
        return {
            "decision": "rejected",
            "decision_reason": (
                "Critical mismatch detected between your Aadhaar and PAN details."
            ),
            "flags": flags,
            "recommendations": [
                "Please ensure the name and date of birth on your Aadhaar and PAN match.",
            ],
        }
    if not faces_detected:
        return {
            "decision": "rejected",
            "decision_reason": "We couldn't detect a face in your selfie.",
            "flags": list(dict.fromkeys([*flags, "no_face_detected"])),
            "recommendations": [
                "Please retake your selfie in good lighting, with your face centred.",
            ],
        }

    if score >= 80 and face_ok:
        return {
            "decision": "approved",
            "decision_reason": (
                "Your Aadhaar and PAN details match and your selfie has been verified."
            ),
            "flags": flags,
            "recommendations": [],
        }

    if score >= 60 or (score >= 40 and not crit):
        recs = ["A human reviewer will take a second look at your submission."]
        if not face_ok:
            recs.append("You may also be asked to retake your selfie.")
        return {
            "decision": "flagged",
            "decision_reason": "Your submission is borderline; we've flagged it for manual review.",
            "flags": flags,
            "recommendations": recs,
        }

    return {
        "decision": "rejected",
        "decision_reason": "Your submission didn't meet our verification thresholds.",
        "flags": flags,
        "recommendations": [
            "Please re-check your documents and try again with clearer images.",
        ],
    }


async def run_decision(state: KYCState, db: AsyncSession) -> dict:
    """Persist the decision + mark the session completed. Returns the delta."""
    # If geolocation already pre-set a rejection (country gate), respect it.
    if state.get("decision") == "rejected" and state.get("decision_reason"):
        result = {
            "decision": state["decision"],
            "decision_reason": state["decision_reason"],
            "flags": list(state.get("flags") or []),
            "recommendations": state.get("recommendations")
            or ["Complete your KYC while connected from within India."],
        }
    else:
        result = compute_decision(state)

    session_uuid = uuid.UUID(state["session_id"])
    await db.execute(
        pg_insert(m.KYCRecord)
        .values(
            session_id=session_uuid,
            decision=result["decision"],
            decision_reason=result["decision_reason"],
            flags=result["flags"],
            recommendations=result["recommendations"],
        )
        .on_conflict_do_update(
            index_elements=["session_id"],
            set_={
                "decision": result["decision"],
                "decision_reason": result["decision_reason"],
                "flags": result["flags"],
                "recommendations": result["recommendations"],
            },
        )
    )
    await db.execute(
        update(m.Session)
        .where(m.Session.id == session_uuid)
        .values(status="completed")
    )
    await db.commit()

    return {
        "decision": result["decision"],
        "decision_reason": result["decision_reason"],
        "flags": result["flags"],
        "recommendations": result["recommendations"],
        "next_required": "done",
    }
