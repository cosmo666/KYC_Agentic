import httpx
import pytest

from app.services.ollama_client import OllamaClient, strip_json_fence


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


def test_strip_json_fence_plain():
    assert strip_json_fence('{"a": 1}') == {"a": 1}


def test_strip_json_fence_markdown_wrapped():
    raw = '```json\n{"a": 1}\n```'
    assert strip_json_fence(raw) == {"a": 1}


def test_strip_json_fence_tolerates_trailing_data():
    """The PAN-upload bug: vision model emitted JSON then a trailing newline +
    extra text. Plain json.loads raises 'Extra data'; raw_decode takes the
    first complete object and ignores the rest."""
    raw = '{"doc_type": "pan", "name": "X"}\n\nSome trailing prose.'
    assert strip_json_fence(raw) == {"doc_type": "pan", "name": "X"}


def test_strip_json_fence_rejects_non_object():
    import json

    with pytest.raises(json.JSONDecodeError):
        strip_json_fence("[1, 2, 3]")


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
