from __future__ import annotations

import json

from app.services.ollama_client import OllamaClient, strip_json_fence

_EXTRACT_PROMPT = """Extract city and state from this Indian address.
Reply ONLY: {"city":"","state":""}. Empty strings if unsure.
Use modern English spellings (Bengaluru not Bangalore, Mumbai not Bombay)."""


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


# ───────────────────────── graph node entry point ─────────────────────────

import ipaddress  # noqa: E402
import uuid  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db import models as _dbm  # noqa: E402
from app.graph.state import KYCState  # noqa: E402
from app.services.ipwhois_client import IPWhoisClient  # noqa: E402


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    )


async def run_geolocation(
    state: KYCState, db: AsyncSession, ollama: OllamaClient
) -> dict:
    """Look up client IP, compare country/city/state against Aadhaar address."""
    raw_ip = state.get("_client_ip") or ""
    # ipwho.is rejects private/loopback/bogon addresses. In dev (Docker bridge)
    # that's almost always the case, so fall back to a public DNS IP.
    ip = raw_ip if _is_public_ip(raw_ip) else "8.8.8.8"
    fallback_used = ip != raw_ip
    print(
        f"[geolocation] raw_ip={raw_ip!r} usable={ip!r} "
        f"fallback={fallback_used}",
        flush=True,
    )

    async with httpx.AsyncClient() as http:
        ipc = IPWhoisClient(http)
        try:
            lookup = await ipc.lookup(ip)
        except Exception as exc:
            print(f"[geolocation] ipwhois lookup failed for {ip}: {exc!r}", flush=True)
            lookup = {
                "ip": ip,
                "country": None,
                "country_code": None,
                "city": None,
                "region": None,
                "raw": {"error": str(exc)},
            }
    print(
        f"[geolocation] resolved {ip} -> "
        f"country={lookup.get('country_code')!r} "
        f"city={lookup.get('city')!r} region={lookup.get('region')!r}",
        flush=True,
    )

    country_ok = (lookup.get("country_code") or "").upper() == "IN"

    aadhaar_slot = state.get("aadhaar", {})
    aadhaar_fields = (
        aadhaar_slot.get("confirmed_json")
        or aadhaar_slot.get("extracted_json")
        or {}
    )
    extracted = await extract_city_state(ollama, aadhaar_fields.get("address", ""))
    aadhaar_city = extracted["city"]
    aadhaar_state = extracted["state"]

    city_match = (
        _case_insensitive_eq(lookup.get("city"), aadhaar_city)
        if aadhaar_city
        else None
    )
    state_match = (
        _case_insensitive_eq(lookup.get("region"), aadhaar_state)
        if aadhaar_state
        else None
    )

    session_uuid = uuid.UUID(state["session_id"])
    await db.execute(
        pg_insert(_dbm.IPCheck)
        .values(
            session_id=session_uuid,
            ip=ip,
            country=lookup.get("country"),
            country_code=lookup.get("country_code"),
            city=lookup.get("city"),
            region=lookup.get("region"),
            aadhaar_city=aadhaar_city or None,
            aadhaar_state=aadhaar_state or None,
            city_match=city_match,
            state_match=state_match,
            country_ok=country_ok,
            raw=lookup.get("raw") or {},
        )
        .on_conflict_do_update(
            index_elements=["session_id"],
            set_={
                "ip": ip,
                "country": lookup.get("country"),
                "country_code": lookup.get("country_code"),
                "city": lookup.get("city"),
                "region": lookup.get("region"),
                "aadhaar_city": aadhaar_city or None,
                "aadhaar_state": aadhaar_state or None,
                "city_match": city_match,
                "state_match": state_match,
                "country_ok": country_ok,
                "raw": lookup.get("raw") or {},
            },
        )
    )
    await db.commit()

    ip_check = {
        "ip": ip,
        "country_code": lookup.get("country_code"),
        "country_ok": country_ok,
        "city": lookup.get("city"),
        "region": lookup.get("region"),
        "city_match": city_match,
        "state_match": state_match,
        # Lat/lon for the FE map preview. Optional — render falls back to
        # the location pill alone when these are missing.
        "latitude": lookup.get("latitude"),
        "longitude": lookup.get("longitude"),
    }

    flags = list(state.get("flags") or [])
    if not country_ok:
        flags.append("ip_country_not_india")
        return {
            "ip_check": ip_check,
            "flags": flags,
            "decision": "rejected",
            "decision_reason": "IP geolocation indicates a non-India country.",
            "next_required": "decide",
        }

    if city_match is False:
        flags.append("ip_city_mismatch")
    if state_match is False:
        flags.append("ip_state_mismatch")

    return {
        "ip_check": ip_check,
        "flags": flags,
        "next_required": "decide",
    }
