from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

CheckStatus = Literal["pass", "fail", "warn", "skip"]


# Indian honorifics + common titles.
_TITLES = [
    "mr",
    "mrs",
    "ms",
    "miss",
    "dr",
    "shri",
    "smt",
    "km",
    "kumari",
    "श्री",
    "श्रीमती",
    "श्रीमान",
    "कुमारी",
    "कुमार",
]
_TITLE_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(t) for t in _TITLES) + r")[\.\s]+",
    flags=re.IGNORECASE,
)


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    t = s.strip()
    t = _TITLE_RE.sub("", t)
    t = t.lower()
    t = re.sub(r"[^\w\sऀ-ॿ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


_DOB_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %m %Y"]


def normalize_dob(s: str | None) -> str:
    if not s:
        return ""
    t = s.strip()
    for fmt in _DOB_FORMATS:
        try:
            return datetime.strptime(t, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return ""


def check_name(aadhaar_name: str | None, pan_name: str | None) -> dict:
    an = normalize_name(aadhaar_name or "")
    pn = normalize_name(pan_name or "")
    if not an or not pn:
        return {
            "name": "name_match",
            "status": "skip",
            "score": 0.5,
            "detail": "one or both names missing",
        }
    score = jaccard(an, pn)
    status: CheckStatus = "pass" if score >= 0.75 else ("warn" if score >= 0.5 else "fail")
    return {
        "name": "name_match",
        "status": status,
        "score": score,
        "detail": f"{an!r} vs {pn!r}",
    }


def check_dob(aadhaar_dob: str | None, pan_dob: str | None) -> dict:
    ad = normalize_dob(aadhaar_dob or "")
    pd = normalize_dob(pan_dob or "")
    if not ad or not pd:
        return {
            "name": "dob_match",
            "status": "skip",
            "score": 0.5,
            "detail": "one or both DOBs missing",
        }
    match = ad == pd
    return {
        "name": "dob_match",
        "status": "pass" if match else "fail",
        "score": 1.0 if match else 0.0,
        "detail": f"{ad} vs {pd}",
    }


def check_doctype(aadhaar: dict, pan: dict) -> dict:
    ok = aadhaar.get("doc_type") == "aadhaar" and pan.get("doc_type") == "pan"
    return {
        "name": "doc_type_sanity",
        "status": "pass" if ok else "fail",
        "score": 1.0 if ok else 0.0,
        "detail": f"aadhaar={aadhaar.get('doc_type')}, pan={pan.get('doc_type')}",
    }


def check_ocr_confidence(aadhaar_conf: str, pan_conf: str) -> dict:
    scale = {"high": 1.0, "medium": 0.6, "low": 0.2}
    score = (scale.get(aadhaar_conf, 0.2) + scale.get(pan_conf, 0.2)) / 2
    status: CheckStatus = "pass" if score >= 0.7 else ("warn" if score >= 0.4 else "fail")
    return {
        "name": "ocr_confidence",
        "status": status,
        "score": score,
        "detail": f"aadhaar={aadhaar_conf}, pan={pan_conf}",
    }


WEIGHTS = {
    "name_match": 0.5,
    "dob_match": 0.3,
    "doc_type_sanity": 0.1,
    "ocr_confidence": 0.1,
}


def cross_validate(
    aadhaar: dict, pan: dict, aadhaar_conf: str, pan_conf: str
) -> dict:
    """Return {overall_score (0..100), checks: [...]}.

    Input dicts are the *confirmed* field dicts (fall back to extracted if unconfirmed).
    """
    checks = [
        check_name(aadhaar.get("name"), pan.get("name")),
        check_dob(aadhaar.get("dob"), pan.get("dob")),
        check_doctype(aadhaar, pan),
        check_ocr_confidence(aadhaar_conf, pan_conf),
    ]
    total = sum(c["score"] * WEIGHTS[c["name"]] for c in checks)
    return {"overall_score": round(total * 100, 1), "checks": checks}


# ───────────────────────── graph node entry point ─────────────────────────

import uuid  # noqa: E402

from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db import models as _dbm  # noqa: E402
from app.graph.state import KYCState  # noqa: E402


async def run_validation(state: KYCState, db: AsyncSession) -> dict:
    """Run cross-doc validation, persist, return the state delta."""
    aadhaar_slot = state.get("aadhaar", {})
    pan_slot = state.get("pan", {})
    aadhaar = (
        aadhaar_slot.get("confirmed_json")
        or aadhaar_slot.get("extracted_json")
        or {}
    )
    pan = pan_slot.get("confirmed_json") or pan_slot.get("extracted_json") or {}
    aa_conf = aadhaar_slot.get("ocr_confidence", "low")
    pan_conf = pan_slot.get("ocr_confidence", "low")

    result = cross_validate(aadhaar, pan, aa_conf, pan_conf)

    session_uuid = uuid.UUID(state["session_id"])
    stmt = pg_insert(_dbm.ValidationResult).values(
        session_id=session_uuid,
        overall_score=result["overall_score"],
        checks=result["checks"],
    ).on_conflict_do_update(
        index_elements=["session_id"],
        set_={
            "overall_score": result["overall_score"],
            "checks": result["checks"],
        },
    )
    await db.execute(stmt)
    await db.commit()

    # Carry over any critical fails as flags (surfaces at decision time).
    flags = list(state.get("flags") or [])
    for c in result["checks"]:
        if c["status"] == "fail" and c["name"] in ("name_match", "dob_match"):
            flags.append(f"{c['name']}_critical_fail")

    return {
        "cross_validation": result,
        "flags": flags,
        "next_required": "wait_for_selfie",
    }
