from __future__ import annotations

import httpx

from app.config import get_settings

# Tiny country-code → name map for the common case in this project. Anything
# not listed falls through to the 2-letter code, which the verdict UI handles
# fine (it only really cares about country_ok = (code == "IN")).
_COUNTRY_NAMES = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "AE": "United Arab Emirates",
    "SG": "Singapore",
    "BD": "Bangladesh",
    "PK": "Pakistan",
    "NP": "Nepal",
    "LK": "Sri Lanka",
}


class IPWhoisClient:
    """IP geolocation lookup with provider fallback.

    Primary: ipinfo.io (free, generally most accurate for India — esp. for
    mobile carriers where ipwho.is sometimes returns the wrong gateway city).
    Fallback: ipwho.is (free, no key, used previously).

    If `IPWHOIS_API_KEY` is set in env, the v2 ipwhois.io endpoint is used
    as the primary instead (paid tier, much higher accuracy).
    """

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def lookup(self, ip: str) -> dict:
        s = get_settings()
        # Paid v2 endpoint takes precedence when the operator has a key.
        if s.ipwhois_api_key:
            try:
                return await self._ipwhois_v2(ip, s.ipwhois_api_key)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[ipgeo] ipwhois.io v2 failed: {exc!r}; falling back to ipinfo.io",
                    flush=True,
                )

        try:
            return await self._ipinfo(ip)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[ipgeo] ipinfo.io failed: {exc!r}; falling back to ipwho.is",
                flush=True,
            )
            return await self._ipwho_is(ip)

    # ── Provider implementations ───────────────────────────────────────

    async def _ipinfo(self, ip: str) -> dict:
        """ipinfo.io free tier — no API key needed for basic city/loc data.

        Returns: {ip, city, region, country, loc:"lat,lon", postal, org, ...}
        """
        r = await self.http.get(f"https://ipinfo.io/{ip}/json", timeout=10)
        r.raise_for_status()
        data = r.json()
        lat, lon = _parse_loc(data.get("loc"))
        cc = data.get("country") or ""
        return {
            "ip": data.get("ip", ip),
            "country": _COUNTRY_NAMES.get(cc, cc) if cc else None,
            "country_code": cc or None,
            "region": data.get("region"),
            "city": data.get("city"),
            "latitude": lat,
            "longitude": lon,
            "raw": {**data, "_source": "ipinfo.io"},
        }

    async def _ipwho_is(self, ip: str) -> dict:
        """ipwho.is fallback — free, no key. Numbers field for lat/lon."""
        r = await self.http.get(f"https://ipwho.is/{ip}", timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "ip": data.get("ip", ip),
            "country": data.get("country"),
            "country_code": data.get("country_code")
            or data.get("country_code_iso3"),
            "region": data.get("region"),
            "city": data.get("city"),
            "latitude": _to_float(data.get("latitude")),
            "longitude": _to_float(data.get("longitude")),
            "raw": {**data, "_source": "ipwho.is"},
        }

    async def _ipwhois_v2(self, ip: str, key: str) -> dict:
        """ipwhois.io v2 (paid) — same shape as ipwho.is."""
        r = await self.http.get(
            f"https://api.ipwhois.io/v2/{ip}",
            params={"key": key},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "ip": data.get("ip", ip),
            "country": data.get("country"),
            "country_code": data.get("country_code")
            or data.get("country_code_iso3"),
            "region": data.get("region"),
            "city": data.get("city"),
            "latitude": _to_float(data.get("latitude")),
            "longitude": _to_float(data.get("longitude")),
            "raw": {**data, "_source": "ipwhois.io-v2"},
        }


# ── helpers ────────────────────────────────────────────────────────────


def _parse_loc(loc: str | None) -> tuple[float | None, float | None]:
    """ipinfo returns 'lat,lon' as a single string."""
    if not loc:
        return None, None
    try:
        a, b = loc.split(",", 1)
        return float(a), float(b)
    except (ValueError, AttributeError):
        return None, None


def _to_float(v: object) -> float | None:
    try:
        return float(v) if v is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
