from __future__ import annotations

import re

from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph

import httpx

from app.agents import orchestrator as orch
from app.agents.biometric import run_biometric
from app.agents.decision import run_decision
from app.agents.geolocation import run_geolocation
from app.agents.intake import run_intake
from app.agents.validation import run_validation
from app.config import get_settings
from app.db.session import SessionLocal
from app.graph.state import KYCState
from app.services.ollama_client import OllamaClient

# Nodes return delta dicts — never the whole state — so the `add_messages`
# reducer on KYCState.messages doesn't double-count anything we didn't touch.


# ───────────────────── helpers ─────────────────────


def _msg_attr(m, key: str) -> str:
    """Read a field from a message that might be a dict or a LangChain BaseMessage."""
    if isinstance(m, BaseMessage):
        if key == "role":
            # BaseMessage subclasses encode role via `.type` (e.g. "human", "ai").
            return {"human": "user", "ai": "assistant", "system": "system"}.get(
                m.type, m.type
            )
        if key == "content":
            return m.content
    if isinstance(m, dict):
        return m.get(key, "")
    return ""


def _last_user_text(state: KYCState) -> str:
    for m in reversed(state.get("messages", [])):
        if _msg_attr(m, "role") == "user":
            return _msg_attr(m, "content")
    return ""


def _extract_name(text: str) -> str:
    t = text.strip()
    for pat in (
        r"^(my name is|i am|i'm|mera naam|mera nam|मेरा नाम)[: ]*",
        r"\bhai\b\s*$",
        r"\bहै\b\s*$",
    ):
        t = re.sub(pat, "", t, flags=re.I).strip()
    # Limit to first 4 tokens, letters + spaces + devanagari
    t = re.sub(r"[^\w\sऀ-ॿ]", "", t)
    return " ".join(t.split()[:4]).strip() or text.strip()[:40]


# ───────────────────── nodes ─────────────────────


async def n_greet(state: KYCState) -> dict:
    """First-ever turn. Seed language, move to the contact form step."""
    last_user = _last_user_text(state)
    language = (
        orch.update_language(dict(state), last_user)
        if last_user
        else (state.get("language") or "en")
    )
    return {"language": language, "next_required": "wait_for_contact"}


async def n_capture_name(state: KYCState) -> dict:
    name = _extract_name(_last_user_text(state))
    return {"user_name": name, "next_required": "wait_for_aadhaar_image"}


async def _intake(state: KYCState, doc_type: str) -> dict:
    # LangGraph nodes don't receive the FastAPI request, so clients are
    # constructed per-invocation. Acceptable for the POC — if this becomes a
    # hot path we can thread them through RunnableConfig instead.
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=180) as http:
        ollama = OllamaClient(
            http=http,
            chat_model=s.chat_model,
            ocr_model=s.ocr_model,
            embed_model=s.embed_model,
        )
        async with SessionLocal() as db:
            return await run_intake(state, db, ollama, doc_type)


async def n_intake_aadhaar(state: KYCState) -> dict:
    return await _intake(state, "aadhaar")


async def n_intake_pan(state: KYCState) -> dict:
    return await _intake(state, "pan")


async def n_validate(state: KYCState) -> dict:
    async with SessionLocal() as db:
        return await run_validation(state, db)


async def n_biometric(state: KYCState) -> dict:
    async with SessionLocal() as db:
        return await run_biometric(state, db)


async def n_geolocation(state: KYCState) -> dict:
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.ollama_base_url, timeout=120) as http:
        ollama = OllamaClient(
            http=http,
            chat_model=s.chat_model,
            ocr_model=s.ocr_model,
            embed_model=s.embed_model,
        )
        async with SessionLocal() as db:
            return await run_geolocation(state, db, ollama)


async def n_decide(state: KYCState) -> dict:
    async with SessionLocal() as db:
        return await run_decision(state, db)


# ───────────────────── routing ─────────────────────

_ROUTE_TARGETS = (
    "intake_aadhaar",
    "intake_pan",
    "validate",
    "biometric",
    "geolocation",
    "decide",
)


def _route_from_current(state: KYCState) -> str:
    nr = state.get("next_required", "wait_for_name")
    # Wait states hand control back to the API caller; the graph halts.
    if nr.startswith("wait_for_") or nr == "done":
        return END
    if nr == "ocr_aadhaar":
        return "intake_aadhaar"
    if nr == "ocr_pan":
        return "intake_pan"
    if nr == "cross_validate":
        return "validate"
    if nr == "biometric":
        return "biometric"
    if nr == "geolocation":
        return "geolocation"
    if nr == "decide":
        return "decide"
    return END


def build_graph():
    g = StateGraph(KYCState)
    g.add_node("greet", n_greet)
    g.add_node("capture_name", n_capture_name)
    g.add_node("intake_aadhaar", n_intake_aadhaar)
    g.add_node("intake_pan", n_intake_pan)
    g.add_node("validate", n_validate)
    g.add_node("biometric", n_biometric)
    g.add_node("geolocation", n_geolocation)
    g.add_node("decide", n_decide)

    def _entry(state: KYCState) -> str:
        nr = state.get("next_required")
        if nr is None:
            return "greet"
        if nr == "wait_for_name":
            return "capture_name"
        return _route_from_current(state)

    g.set_conditional_entry_point(
        _entry,
        {
            "greet": "greet",
            "capture_name": "capture_name",
            "intake_aadhaar": "intake_aadhaar",
            "intake_pan": "intake_pan",
            "validate": "validate",
            "biometric": "biometric",
            "geolocation": "geolocation",
            "decide": "decide",
            END: END,
        },
    )

    for node in (
        "greet",
        "capture_name",
        "intake_aadhaar",
        "intake_pan",
        "validate",
        "biometric",
        "geolocation",
        "decide",
    ):
        g.add_conditional_edges(
            node,
            _route_from_current,
            {
                "intake_aadhaar": "intake_aadhaar",
                "intake_pan": "intake_pan",
                "validate": "validate",
                "biometric": "biometric",
                "geolocation": "geolocation",
                "decide": "decide",
                END: END,
            },
        )

    return g
