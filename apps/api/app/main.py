import asyncio
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import capture as capture_router
from app.routers import chat as chat_router
from app.routers import confirm as confirm_router
from app.routers import files as files_router
from app.routers import session as session_router
from app.routers import upload as upload_router
from app.services.ollama_client import OllamaClient
from app.utils import get_client_ip


async def _warm_deepface_async() -> None:
    """Background task — pull VGG-Face into RAM so the first /capture is fast.

    DeepFace.verify is sync + CPU-bound; run it off the event loop.
    Weights live on the `deepface_cache` docker volume so this only re-downloads
    if the volume is wiped.
    """
    from app.services.deepface_runner import warm

    print("[lifespan] warming DeepFace (first boot may download ~580 MB)…", flush=True)
    await asyncio.to_thread(warm)
    print("[lifespan] DeepFace ready", flush=True)


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
    warm_task = asyncio.create_task(_warm_deepface_async())
    yield
    warm_task.cancel()
    await http.aclose()


app = FastAPI(title="KYC Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Allow any localhost / 127.0.0.1 port — covers Vite dev (5173), the
    # docker web container (5174 when 5173 is held), and ad-hoc previews.
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    # `*` doesn't always cover custom headers under credentials; list the ones
    # the FE actually sends so CORS preflights pass cleanly.
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Real-IP",
        "X-Forwarded-For",
        "*",
    ],
    expose_headers=["X-Resolved-IP"],
)


@app.middleware("http")
async def request_log(request: Request, call_next):
    """One-line request log per call. Surfaces method, path, X-Real-IP (the
    client-supplied public IP), socket peer, status, and ms — so when geo or
    auth misbehaves it's instantly clear whether the FE sent the header,
    whether the backend extracted it, and whether the request reached the
    intended handler.
    """
    start = time.perf_counter()
    real = request.headers.get("x-real-ip", "")
    fwd = request.headers.get("x-forwarded-for", "")
    peer = request.client.host if request.client else "?"
    resolved = get_client_ip(request)
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    print(
        f"[req] {request.method} {request.url.path} "
        f"-> {response.status_code} ({ms:.0f} ms) "
        f"| peer={peer} x-real-ip={real or '-'} xff={fwd or '-'} "
        f"resolved={resolved}",
        flush=True,
    )
    response.headers["X-Resolved-IP"] = resolved
    return response


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


@app.get("/debug/whoami")
async def whoami(request: Request):
    """Diagnostic — returns exactly what the backend sees for the caller's IP.

    Use this to verify the FE is sending X-Real-IP correctly:
      curl -H "X-Real-IP: 1.2.3.4" http://localhost:8000/debug/whoami
    """
    return {
        "headers": {
            "x-real-ip": request.headers.get("x-real-ip"),
            "x-forwarded-for": request.headers.get("x-forwarded-for"),
            "origin": request.headers.get("origin"),
            "user-agent": request.headers.get("user-agent"),
        },
        "socket_peer": request.client.host if request.client else None,
        "resolved_client_ip": get_client_ip(request),
    }


app.include_router(chat_router.router)
app.include_router(upload_router.router)
app.include_router(confirm_router.router)
app.include_router(capture_router.router)
app.include_router(session_router.router)
app.include_router(files_router.router)
