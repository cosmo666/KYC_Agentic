# backend/routers/validation.py

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from services.workflow_service import run_kyc_workflow, kyc_state_to_dict

router = APIRouter(prefix="/validate", tags=["Validation"])


class ValidationRequest(BaseModel):
    documents: List[dict]           # list of extracted_data dicts from /upload-doc
    face_verified: bool = False
    face_confidence: float = 0.0


@router.post("/")
def run_validation(req: ValidationRequest):
    """
    Run the KYC agentic workflow:
    1. Classify documents (Aadhaar vs PAN)
    2. Check completeness
    3. Cross-validate fields
    4. Factor in face verification
    5. Produce a final decision: approved | flagged | rejected | incomplete
    """
    state = run_kyc_workflow(
        documents=req.documents,
        face_verified=req.face_verified,
        face_confidence=req.face_confidence,
    )
    return kyc_state_to_dict(state)
