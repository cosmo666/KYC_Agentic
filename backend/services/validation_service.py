# backend/services/validation_service.py
"""
Cross-validation engine: compares extracted data from Aadhaar and PAN cards.
Returns a structured verdict used by the workflow engine.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data Types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationCheck:
    field: str
    status: str          # "pass" | "fail" | "warn" | "skip"
    aadhaar_value: Optional[str]
    pan_value: Optional[str]
    message: str
    score: float         # 0.0 – 1.0


@dataclass
class ValidationResult:
    checks: list[ValidationCheck] = field(default_factory=list)
    overall_score: float = 0.0   # 0–100
    verdict: str = "pending"     # "approved" | "flagged" | "rejected"
    reason: str = ""
    name_match_score: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_name(name: Optional[str]) -> str:
    """Lowercase, strip extra spaces, remove titles."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common titles
    for title in ["mr.", "mrs.", "ms.", "dr.", "shri", "smt.", "km.", "kumari"]:
        name = name.replace(title, "")
    # Collapse whitespace
    return re.sub(r"\s+", " ", name).strip()


def _fuzzy_name_score(a: str, b: str) -> float:
    """
    Simple token-based similarity.
    Returns 0.0 – 1.0.
    Does NOT require any third-party lib.
    """
    if not a or not b:
        return 0.0
    tokens_a = set(_normalize_name(a).split())
    tokens_b = set(_normalize_name(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)  # Jaccard similarity


def _normalize_dob(dob: Optional[str]) -> Optional[str]:
    """Normalize various date formats to DD/MM/YYYY."""
    if not dob:
        return None
    # Try common patterns
    patterns = [
        (r"(\d{2})[/-](\d{2})[/-](\d{4})", r"\1/\2/\3"),  # DD-MM-YYYY or DD/MM/YYYY
        (r"(\d{4})[/-](\d{2})[/-](\d{2})", None),           # YYYY-MM-DD → reformat
    ]
    dob = dob.strip()
    m = re.match(r"(\d{4})[/-](\d{2})[/-](\d{2})", dob)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", dob)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return dob


# ─────────────────────────────────────────────────────────────────────────────
# Core Validation Engine
# ─────────────────────────────────────────────────────────────────────────────

def validate_documents(aadhaar_data: dict, pan_data: dict) -> ValidationResult:
    """
    Compare extracted Aadhaar and PAN data.
    Returns a ValidationResult with individual checks and an overall verdict.
    """
    result = ValidationResult()
    checks = []
    weighted_scores = []  # (score, weight) tuples

    # ── 1. Name Match (most important — weight 0.5) ──────────────────────────
    aadhaar_name = aadhaar_data.get("name")
    pan_name = pan_data.get("name")

    name_score = _fuzzy_name_score(aadhaar_name, pan_name)
    result.name_match_score = round(name_score * 100, 1)

    if name_score >= 0.80:
        name_status, name_msg = "pass", f"Names match ({result.name_match_score}% similarity)"
    elif name_score >= 0.50:
        name_status, name_msg = "warn", f"Names partially match ({result.name_match_score}% similarity) – possible spelling variation"
    elif aadhaar_name and pan_name:
        name_status, name_msg = "fail", f"Names do not match ({result.name_match_score}% similarity)"
    else:
        name_status, name_msg = "skip", "Name not found on one or both documents"

    checks.append(ValidationCheck(
        field="Full Name",
        status=name_status,
        aadhaar_value=aadhaar_name,
        pan_value=pan_name,
        message=name_msg,
        score=name_score,
    ))
    weighted_scores.append((name_score, 0.5))

    # ── 2. Date of Birth Match (weight 0.3) ──────────────────────────────────
    aadhaar_dob = _normalize_dob(aadhaar_data.get("dob"))
    pan_dob = _normalize_dob(pan_data.get("dob"))

    if aadhaar_dob and pan_dob:
        dob_match = aadhaar_dob == pan_dob
        dob_score = 1.0 if dob_match else 0.0
        checks.append(ValidationCheck(
            field="Date of Birth",
            status="pass" if dob_match else "fail",
            aadhaar_value=aadhaar_dob,
            pan_value=pan_dob,
            message="Dates of birth match" if dob_match else "Dates of birth do not match",
            score=dob_score,
        ))
        weighted_scores.append((dob_score, 0.3))
    else:
        checks.append(ValidationCheck(
            field="Date of Birth",
            status="skip",
            aadhaar_value=aadhaar_dob,
            pan_value=pan_dob,
            message="Date of birth not available on one or both documents",
            score=0.5,  # neutral
        ))
        weighted_scores.append((0.5, 0.3))

    # ── 3. Document Type Validation (weight 0.1) ─────────────────────────────
    aadhaar_type = aadhaar_data.get("document_type", "").lower()
    pan_type = pan_data.get("document_type", "").lower()

    doc_types_ok = (aadhaar_type == "aadhaar") and (pan_type == "pan")
    checks.append(ValidationCheck(
        field="Document Types",
        status="pass" if doc_types_ok else "warn",
        aadhaar_value=aadhaar_type or "undetected",
        pan_value=pan_type or "undetected",
        message="Both document types correctly identified" if doc_types_ok
                else f"Document type mismatch – detected: {aadhaar_type}, {pan_type}",
        score=1.0 if doc_types_ok else 0.3,
    ))
    weighted_scores.append((1.0 if doc_types_ok else 0.3, 0.1))

    # ── 4. OCR Confidence (weight 0.1) ───────────────────────────────────────
    conf_map = {"high": 1.0, "medium": 0.6, "low": 0.2}
    aadhaar_conf = conf_map.get(aadhaar_data.get("confidence", "low"), 0.2)
    pan_conf = conf_map.get(pan_data.get("confidence", "low"), 0.2)
    avg_conf = (aadhaar_conf + pan_conf) / 2

    checks.append(ValidationCheck(
        field="OCR Confidence",
        status="pass" if avg_conf >= 0.6 else ("warn" if avg_conf >= 0.3 else "fail"),
        aadhaar_value=aadhaar_data.get("confidence", "unknown"),
        pan_value=pan_data.get("confidence", "unknown"),
        message=f"Document readability: {'Good' if avg_conf >= 0.6 else 'Poor'}",
        score=avg_conf,
    ))
    weighted_scores.append((avg_conf, 0.1))

    # ── Overall Score ─────────────────────────────────────────────────────────
    total_weight = sum(w for _, w in weighted_scores)
    raw_score = sum(s * w for s, w in weighted_scores) / total_weight
    result.overall_score = round(raw_score * 100, 1)
    result.checks = checks

    return result
