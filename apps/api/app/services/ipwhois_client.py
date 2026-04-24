import httpx

from app.config import get_settings


class IPWhoisClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def lookup(self, ip: str) -> dict:
        s = get_settings()
        params: dict = {}
        if s.ipwhois_api_key:
            params["key"] = s.ipwhois_api_key
        # Free tier: https://ipwho.is/<ip>
        url = (
            f"https://api.ipwhois.io/v2/{ip}"
            if s.ipwhois_api_key
            else f"https://ipwho.is/{ip}"
        )
        r = await self.http.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "ip": data.get("ip", ip),
            "country": data.get("country"),
            "country_code": data.get("country_code") or data.get("country_code_iso3"),
            "region": data.get("region"),
            "city": data.get("city"),
            "raw": data,
        }
