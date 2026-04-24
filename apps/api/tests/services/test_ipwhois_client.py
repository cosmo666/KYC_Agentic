import httpx
import pytest

from app.services.ipwhois_client import IPWhoisClient


@pytest.mark.asyncio
async def test_lookup_returns_parsed_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ip": "1.2.3.4",
                "country": "India",
                "country_code": "IN",
                "region": "Maharashtra",
                "city": "Mumbai",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake") as http:
        c = IPWhoisClient(http=http)
        res = await c.lookup("1.2.3.4")
        assert res["country_code"] == "IN"
        assert res["city"] == "Mumbai"
