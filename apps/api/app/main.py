import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    app.state.http = httpx.AsyncClient(timeout=30)
    yield
    # shutdown
    await app.state.http.aclose()


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
