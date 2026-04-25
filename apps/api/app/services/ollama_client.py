from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx


class OllamaClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        chat_model: str,
        ocr_model: str,
        embed_model: str,
    ):
        self.http = http
        self.chat_model = chat_model
        self.ocr_model = ocr_model
        self.embed_model = embed_model

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        payload: dict = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        r = await self.http.post("/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def vision_extract(self, prompt: str, image_path: str | Path) -> str:
        """Send a vision prompt with an image; return raw model output (may be JSON string)."""
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        payload = {
            "model": self.ocr_model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        r = await self.http.post("/api/chat", json=payload, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def embed(self, text: str) -> list[float]:
        payload = {"model": self.embed_model, "prompt": text}
        r = await self.http.post("/api/embeddings", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]


def strip_json_fence(raw: str) -> dict:
    """Best-effort parse of vision-model output.

    Handles three real-world cases observed from Ollama vision models:
    1. Plain JSON object.
    2. Fenced JSON: ```json ... ``` or just ``` ... ```.
    3. JSON followed by trailing prose / newlines / a second snippet — we
       use raw_decode to take the first complete object and ignore the rest.
    """
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        if s.lstrip().lower().startswith("json"):
            s = s.split("\n", 1)[1] if "\n" in s else s
    s = s.strip()
    # strict=False allows literal tabs/newlines inside string values — vision
    # models routinely emit them in multi-line fields like Aadhaar addresses.
    decoder = json.JSONDecoder(strict=False)
    obj, _ = decoder.raw_decode(s)
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("expected object", s, 0)
    return obj
