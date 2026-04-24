from unittest.mock import AsyncMock

import pytest

from app.agents.geolocation import extract_city_state


@pytest.mark.asyncio
async def test_extract_city_state_parses_json():
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value='{"city": "Mumbai", "state": "Maharashtra"}')
    result = await extract_city_state(
        fake, "123 Main Rd, Andheri, Mumbai 400058, Maharashtra, India"
    )
    assert result == {"city": "Mumbai", "state": "Maharashtra"}


@pytest.mark.asyncio
async def test_extract_city_state_handles_fenced_json():
    fake = AsyncMock()
    fake.chat = AsyncMock(
        return_value='```json\n{"city": "Bengaluru", "state": "Karnataka"}\n```'
    )
    result = await extract_city_state(fake, "some address Bengaluru KA")
    assert result["city"] == "Bengaluru"


@pytest.mark.asyncio
async def test_extract_city_state_returns_empty_on_bad_json():
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value="not json at all")
    result = await extract_city_state(fake, "address")
    assert result == {"city": "", "state": ""}
