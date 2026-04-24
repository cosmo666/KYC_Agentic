# backend/main.py

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import PORT
from routers import documents
from routers import chat
from routers import face
from routers import validation

# ─────────────────────────────────────────────────────────────────────────────
# App Init
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="KYC Assistant API",
    description="Intelligent KYC document processing with local Ollama Vision",
    version="2.0.0",
    docs_url="/docs",       # Swagger UI at /docs
    redoc_url="/redoc",     # ReDoc at /redoc
)

# ─────────────────────────────────────────────────────────────────────────────
# CORS — Allow React frontend on port 3000 to call this backend
# ─────────────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # React dev server
        "http://127.0.0.1:3000",
        "http://localhost:3001",    # React alt port
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(face.router)
app.include_router(validation.router)

# Keep /upload-doc at root level for backward compatibility with your frontend
from routers.documents import upload_document
from fastapi import File, UploadFile

@app.post("/upload-doc", tags=["Legacy"])
async def upload_doc_root(file: UploadFile = File(...)):
    """
    Backward-compatible route — your frontend calls this.
    Internally calls the same logic as /documents/upload.
    """
    return await upload_document(file=file)

# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "message": "KYC Assistant API is running 🚀",
        "version": "2.0.0",
        "docs": "/docs",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=PORT,
        reload=True,      # Auto-reload on code changes
    )
