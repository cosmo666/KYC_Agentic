import httpx
import pytest

from app.services.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_chat_returns_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": "hi there"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake") as http:
        c = OllamaClient(http=http, chat_model="m", ocr_model="v", embed_model="e")
        reply = await c.chat([{"role": "user", "content": "hello"}])
        assert reply == "hi there"


@pytest.mark.asyncio
async def test_embed_returns_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake") as http:
        c = OllamaClient(http=http, chat_model="m", ocr_model="v", embed_model="e")
        vec = await c.embed("hello")
        assert vec == [0.1, 0.2, 0.3]
