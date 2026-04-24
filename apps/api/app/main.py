from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat as chat_router
from app.services.ollama_client import OllamaClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http = httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=180)
    app.state.http = http
    app.state.ollama = OllamaClient(
        http=http,
        chat_model=settings.chat_model,
        ocr_model=settings.ocr_model,
        embed_model=settings.embed_model,
    )
    yield
    await http.aclose()


app = FastAPI(title="KYC Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    settings = get_settings()
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                ollama_status = "reachable"
    except Exception:
        pass
    return {"status": "ok", "ollama": ollama_status}


app.include_router(chat_router.router)
