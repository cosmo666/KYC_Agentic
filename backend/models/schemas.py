# backend/models/schemas.py

from pydantic import BaseModel
from typing import Optional, List


class ExtractedData(BaseModel):
    document_type: str          # "aadhaar" | "pan" | "passport" | "unknown"
    name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    aadhaar_number: Optional[str] = None
    pan_number: Optional[str] = None
    address: Optional[str] = None
    fathers_name: Optional[str] = None   # PAN cards have this
    confidence: Optional[str] = None     # "high" | "medium" | "low"


class UploadResponse(BaseModel):
    success: bool
    message: str
    filename: str
    raw_text: Optional[str] = None
    extracted_data: Optional[ExtractedData] = None
    error: Optional[str] = None
