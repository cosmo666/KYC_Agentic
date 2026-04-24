from __future__ import annotations

import json

from app.services.ollama_client import OllamaClient, strip_json_fence

_EXTRACT_PROMPT = """Given an Indian address, extract the city and state.
Reply with ONLY a JSON object: {"city": "", "state": ""}. Use empty strings if unsure.
Normalise to commonly used English spellings (e.g. "Bengaluru", not "Bangaluru";
"Mumbai", not "Bombay")."""


async def extract_city_state(ollama: OllamaClient, address: str) -> dict:
    if not address:
        return {"city": "", "state": ""}
    try:
        raw = await ollama.chat(
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": address},
            ],
            json_mode=True,
            temperature=0.0,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = strip_json_fence(raw)
            except json.JSONDecodeError:
                return {"city": "", "state": ""}
        return {"city": data.get("city", ""), "state": data.get("state", "")}
    except Exception:
        return {"city": "", "state": ""}


def _case_insensitive_eq(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().casefold() == b.strip().casefold()
