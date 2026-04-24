# backend/config.py

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "uploads")
PORT: int = int(os.getenv("PORT", "9090"))

# Allowed file types for document upload
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf"}

# Tesseract path (Windows fallback)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
