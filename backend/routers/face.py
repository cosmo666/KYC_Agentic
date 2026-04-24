# backend/routers/face.py

import os
import uuid
from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel
from typing import Optional
from config import UPLOAD_FOLDER
from services.face_service import verify_faces

router = APIRouter(tags=["Face Verification"])


class FaceVerifyResponse(BaseModel):
    verified: bool
    confidence: float
    distance: Optional[float] = None
    threshold: Optional[float] = None
    model: str = "VGG-Face"
    faces_detected: bool = True
    error: Optional[str] = None
    message: str = ""


@router.post("/verify-face", response_model=FaceVerifyResponse)
async def verify_face(
    selfie: UploadFile = File(..., description="Selfie image of the user"),
    document: UploadFile = File(..., description="Document image (Aadhaar/PAN with photo)"),
):
    """
    Compare a user's selfie with the photo on their KYC document.
    Returns a match confidence score.
    """
    # Validate file types
    allowed = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
    for f in [selfie, document]:
        if f.content_type not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {f.content_type}. Use JPG, PNG, or WEBP."
            )

    # Save files temporarily
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    selfie_id = str(uuid.uuid4())[:8]
    doc_id = str(uuid.uuid4())[:8]
    
    selfie_ext = os.path.splitext(selfie.filename)[1] or ".jpg"
    doc_ext = os.path.splitext(document.filename)[1] or ".jpg"
    
    selfie_path = os.path.join(UPLOAD_FOLDER, f"selfie_{selfie_id}{selfie_ext}")
    doc_path = os.path.join(UPLOAD_FOLDER, f"doc_{doc_id}{doc_ext}")

    try:
        # Write selfie
        with open(selfie_path, "wb") as f:
            content = await selfie.read()
            f.write(content)

        # Write document
        with open(doc_path, "wb") as f:
            content = await document.read()
            f.write(content)

        # Run face verification
        result = verify_faces(selfie_path, doc_path)

        # Build message
        if not result.get("faces_detected", True):
            message = result.get("error", "Could not detect faces.")
        elif result.get("verified"):
            conf = result["confidence"]
            if conf >= 80:
                message = f"✅ Strong match! ({conf}% confidence). Identity verified."
            elif conf >= 60:
                message = f"✅ Likely match ({conf}% confidence). Proceed with caution."
            else:
                message = f"⚠️ Weak match ({conf}% confidence). Manual review recommended."
        else:
            message = f"❌ Faces do not match ({result['confidence']}% confidence). Please try again with a clearer photo."

        return FaceVerifyResponse(
            verified=result.get("verified", False),
            confidence=result.get("confidence", 0),
            distance=result.get("distance"),
            threshold=result.get("threshold"),
            model=result.get("model", "VGG-Face"),
            faces_detected=result.get("faces_detected", False),
            error=result.get("error"),
            message=message,
        )

    finally:
        # Cleanup temp files
        for p in [selfie_path, doc_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
