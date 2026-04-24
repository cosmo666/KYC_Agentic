# backend/services/ocr_service.py

import os
import re
import json
import base64
import pytesseract
import google.generativeai as genai

from PIL import Image
from config import GEMINI_API_KEY, TESSERACT_CMD
from models.schemas import ExtractedData

# ── Configure Tesseract (fallback) ──────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

import ollama

# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA VISION — Primary OCR engine
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """
You are an expert KYC document analyzer for Indian documents.

Analyze this document image carefully and extract all information.

Return ONLY a valid JSON object — no markdown, no explanation — in this exact format:
{
  "document_type": "aadhaar" | "pan" | "passport" | "unknown",
  "name": "Full name as printed on the document or null",
  "dob": "DD/MM/YYYY format or null",
  "gender": "Male" | "Female" | "Other" or null,
  "aadhaar_number": "XXXX XXXX XXXX format or null",
  "pan_number": "XXXXX9999X format (5 letters, 4 digits, 1 letter) or null",
  "address": "Full address as printed or null",
  "fathers_name": "Father's name (PAN cards) or null",
  "confidence": "high" | "medium" | "low"
}

Rules:
- For Aadhaar: mask first 8 digits → XXXX XXXX 1234
- For Hindi text: translate to English
- If a field is not visible or not applicable, return null
- confidence = "high" if all main fields found, "medium" if partial, "low" if unreadable
"""


def extract_with_ollama(image_path: str) -> dict:
    """
    Primary extraction using Ollama with gemma3:4b-cloud.
    Returns a dict matching ExtractedData schema.
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    try:
        response = ollama.chat(
            model='gemma3:4b-cloud',
            messages=[{
                'role': 'user',
                'content': EXTRACTION_PROMPT,
                'images': [image_path]
            }],
            options={'temperature': 0.1}
        )

        raw_output = response['message']['content'].strip()

        # Strip markdown code fences if wrapped in ```json ... ```
        if raw_output.startswith("```"):
            raw_output = re.sub(r"^```[a-z]*\n?", "", raw_output)
            raw_output = re.sub(r"\n?```$", "", raw_output)

        return json.loads(raw_output)

    except Exception as e:
        raise Exception(f"Ollama extraction failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# TESSERACT — Fallback OCR engine
# ─────────────────────────────────────────────────────────────────────────────

def extract_with_tesseract(image_path: str) -> dict:
    """
    Fallback extraction using Tesseract + regex.
    Less accurate but works offline / without API key.
    """
    text = pytesseract.image_to_string(Image.open(image_path))
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Detect document type
    text_lower = text.lower()
    if "aadhaar" in text_lower or "uidai" in text_lower or "unique identification" in text_lower:
        doc_type = "aadhaar"
    elif "income tax" in text_lower or "permanent account" in text_lower:
        doc_type = "pan"
    elif "passport" in text_lower or "republic of india" in text_lower:
        doc_type = "passport"
    else:
        doc_type = "unknown"

    # ── Aadhaar number ────────────────────────────────────────────────────────
    aadhaar = None
    numbers = re.findall(r"\d+", text)
    for i in range(len(numbers) - 2):
        candidate = numbers[i] + numbers[i + 1] + numbers[i + 2]
        if len(candidate) == 12:
            aadhaar = f"XXXX XXXX {candidate[8:]}"  # Mask first 8
            break

    # ── PAN number ────────────────────────────────────────────────────────────
    pan_match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text)
    pan = pan_match.group() if pan_match else None

    # ── DOB ───────────────────────────────────────────────────────────────────
    dob_match = re.search(r"\d{2}/\d{2}/\d{4}", text)
    dob = dob_match.group() if dob_match else None

    # ── Gender ────────────────────────────────────────────────────────────────
    gender = None
    if re.search(r"\bMALE\b|\bpurush\b", text, re.IGNORECASE):
        gender = "Male"
    elif re.search(r"\bFEMALE\b|\bmahila\b", text, re.IGNORECASE):
        gender = "Female"

    # ── Name (heuristic: first clean line) ───────────────────────────────────
    name = lines[0] if lines else None

    return {
        "document_type": doc_type,
        "name": name,
        "dob": dob,
        "gender": gender,
        "aadhaar_number": aadhaar,
        "pan_number": pan,
        "address": None,       # Tesseract can't reliably extract address blocks
        "fathers_name": None,
        "confidence": "low",   # Always low for Tesseract fallback
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC FUNCTION — Called by the router
# ─────────────────────────────────────────────────────────────────────────────

def process_document(image_path: str) -> tuple[ExtractedData, str]:
    """
    Tries Ollama first. Falls back to Tesseract if Ollama fails.
    Returns: (ExtractedData, engine_used)
    """
    try:
        result = extract_with_ollama(image_path)
        return ExtractedData(**result), "ollama"
    except Exception as e:
        print(f"[OCR] Ollama failed: {e} — falling back to Tesseract")

    # Tesseract fallback
    result = extract_with_tesseract(image_path)
    return ExtractedData(**result), "tesseract"
