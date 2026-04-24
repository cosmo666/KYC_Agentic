# backend/services/workflow_service.py
"""
LangGraph-style agentic decision workflow.
Processes validation results through a state machine to produce:
  - APPROVED       → all checks pass, high confidence
  - FLAGGED        → borderline, needs human review
  - REJECTED       → critical failures
  - INCOMPLETE     → missing required documents
"""

from dataclasses import dataclass, field
from typing import Optional
from services.validation_service import ValidationResult, validate_documents


# ─────────────────────────────────────────────────────────────────────────────
# Workflow State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KYCState:
    # Inputs
    documents: list[dict] = field(default_factory=list)   # list of extracted_data dicts
    face_verified: bool = False
    face_confidence: float = 0.0

    # Produced by nodes
    aadhaar_data: Optional[dict] = None
    pan_data: Optional[dict] = None
    validation: Optional[ValidationResult] = None

    # Final output
    decision: str = "pending"   # "approved" | "flagged" | "rejected" | "incomplete"
    decision_reason: str = ""
    flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Node Functions  (each is a pure function: state → state)
# ─────────────────────────────────────────────────────────────────────────────

def node_classify_documents(state: KYCState) -> KYCState:
    """Identify which document is Aadhaar and which is PAN."""
    for doc in state.documents:
        doc_type = (doc.get("document_type") or "").lower()
        if doc_type == "aadhaar" and state.aadhaar_data is None:
            state.aadhaar_data = doc
        elif doc_type == "pan" and state.pan_data is None:
            state.pan_data = doc
    return state


def node_check_completeness(state: KYCState) -> KYCState:
    """Verify that both required documents are present."""
    if state.aadhaar_data is None:
        state.flags.append("Missing Aadhaar card")
        state.recommendations.append("Please re-upload your Aadhaar card")
    if state.pan_data is None:
        state.flags.append("Missing PAN card")
        state.recommendations.append("Please re-upload your PAN card")

    if state.aadhaar_data is None or state.pan_data is None:
        state.decision = "incomplete"
        state.decision_reason = "One or more required documents are missing"
    return state


def node_cross_validate(state: KYCState) -> KYCState:
    """Run cross-validation between Aadhaar and PAN."""
    if state.decision == "incomplete":
        return state   # Skip — already decided

    result = validate_documents(state.aadhaar_data, state.pan_data)
    state.validation = result

    # Collect warnings from individual checks
    for check in result.checks:
        if check.status == "fail":
            state.flags.append(f"{check.field}: {check.message}")
        elif check.status == "warn":
            state.flags.append(f"⚠️ {check.field}: {check.message}")

    return state


def node_evaluate_face(state: KYCState) -> KYCState:
    """Factor in face-verification confidence."""
    if not state.face_verified:
        if state.face_confidence < 30:
            state.flags.append("Face verification failed or was skipped")
            state.recommendations.append("Re-take selfie in a well-lit environment")
        elif state.face_confidence < 60:
            state.flags.append(f"⚠️ Low face-match confidence ({state.face_confidence:.0f}%)")
    return state


def node_make_decision(state: KYCState) -> KYCState:
    """
    Final decision node.

    Score thresholds:
      ≥ 80  + face OK  → APPROVED
      60–79 OR face low → FLAGGED
      < 60  OR critical fail → REJECTED
    """
    if state.decision == "incomplete":
        return state

    score = state.validation.overall_score if state.validation else 0
    critical_fails = [c for c in (state.validation.checks if state.validation else [])
                      if c.status == "fail" and c.field in ("Full Name", "Date of Birth")]

    face_ok = state.face_verified or state.face_confidence >= 60

    if critical_fails:
        state.decision = "rejected"
        state.decision_reason = (
            f"Critical mismatch detected: {critical_fails[0].message}. "
            "The Aadhaar and PAN do not appear to belong to the same person."
        )
        state.recommendations.append("Ensure both documents belong to the same individual")

    elif score >= 80 and face_ok:
        state.decision = "approved"
        state.decision_reason = (
            f"All checks passed with {score:.0f}% confidence. "
            "Identity successfully verified."
        )

    elif score >= 60 or (score >= 40 and not critical_fails):
        state.decision = "flagged"
        state.decision_reason = (
            f"Verification score {score:.0f}% is borderline. "
            "Application flagged for manual review."
        )
        state.recommendations.append("A KYC officer will review your application within 24 hours")

    else:
        state.decision = "rejected"
        state.decision_reason = (
            f"Verification score too low ({score:.0f}%). "
            "Document data could not be confirmed."
        )
        state.recommendations.append("Please retake clearer photos of your documents")

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Graph Runner
# ─────────────────────────────────────────────────────────────────────────────

# LangGraph-style pipeline: ordered list of nodes
WORKFLOW_GRAPH = [
    node_classify_documents,
    node_check_completeness,
    node_cross_validate,
    node_evaluate_face,
    node_make_decision,
]


def run_kyc_workflow(
    documents: list[dict],
    face_verified: bool = False,
    face_confidence: float = 0.0,
) -> KYCState:
    """
    Execute the full KYC agentic workflow.
    Returns a KYCState with the final decision, flags, and recommendations.
    """
    state = KYCState(
        documents=documents,
        face_verified=face_verified,
        face_confidence=face_confidence,
    )
    for node in WORKFLOW_GRAPH:
        state = node(state)
    return state


def kyc_state_to_dict(state: KYCState) -> dict:
    """Serialize KYCState to a JSON-safe dict for the API response."""
    checks = []
    if state.validation:
        for c in state.validation.checks:
            checks.append({
                "field": c.field,
                "status": c.status,
                "aadhaar_value": c.aadhaar_value,
                "pan_value": c.pan_value,
                "message": c.message,
                "score": round(c.score * 100, 1),
            })

    return {
        "decision": state.decision,
        "decision_reason": state.decision_reason,
        "overall_score": state.validation.overall_score if state.validation else 0,
        "name_match_score": state.validation.name_match_score if state.validation else 0,
        "face_verified": state.face_verified,
        "face_confidence": state.face_confidence,
        "checks": checks,
        "flags": state.flags,
        "recommendations": state.recommendations,
    }
