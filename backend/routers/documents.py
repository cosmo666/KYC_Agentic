# backend/routers/documents.py

import os
import uuid
import shutil

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS
from services.ocr_service import process_document
from models.schemas import UploadResponse

router = APIRouter(prefix="/documents", tags=["Documents"])

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _allowed_file(filename: str) -> bool:
    """Check if the file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a KYC document (Aadhaar / PAN / Passport).
    Extracts structured data using Gemini Vision (fallback: Tesseract).
    """

    # ── Validate file ─────────────────────────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    if not _allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── Save file with unique name to avoid collisions ────────────────────────
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # ── Run OCR + Extraction ──────────────────────────────────────────────────
    try:
        extracted_data, engine_used = process_document(file_path)
    except Exception as e:
        # Clean up saved file on failure
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

    return UploadResponse(
        success=True,
        message=f"Document processed successfully using {engine_used}.",
        filename=unique_filename,
        extracted_data=extracted_data,
    )


# ── Keep old /upload-doc route for backward compatibility ─────────────────────
# (Your frontend currently calls this URL)
@router.post("/upload-doc-legacy", include_in_schema=False)
async def upload_doc_legacy(file: UploadFile = File(...)):
    return await upload_document(file=file)
