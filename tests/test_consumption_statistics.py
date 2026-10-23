"""Tests for authenticated, privacy-safe meter consumption aggregation."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, site: str | None = "test-site") -> FrankEnergieService:
    """Construct a mock-backed authenticated service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


@pytest.mark.asyncio
async def test_consumption_aggregates_only_selected_days() -> None:
    """Exclude user IDs, other dates and individual readings from the result."""
    client = AsyncMock()
    client.meter_readings.return_value = SimpleNamespace(
        user_id="private-user",
        daily_consumption=[
            SimpleNamespace(date="2026-10-01", consumption_kwh=2.5),
            SimpleNamespace(date="2026-10-02", consumption_kwh=3.5),
            SimpleNamespace(date="2026-10-03", consumption_kwh=99.0),
        ],
    )
    result = await make_service(client).get_daily_consumption_statistics(
        date(2026, 10, 1), date(2026, 10, 2)
    )
    assert result == {
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "day_count": 2,
        "total_kwh": 6.0,
        "average_daily_kwh": 3.0,
    }
    assert "private" not in str(result)
    client.meter_readings.assert_awaited_once_with("test-site")


@pytest.mark.asyncio
async def test_consumption_empty_and_missing() -> None:
    """Distinguish zero observations from zero average consumption."""
    client = AsyncMock()
    client.meter_readings.return_value = None
    result = await make_service(client).get_daily_consumption_statistics(
        date(2026, 10, 1), date(2026, 10, 2)
    )
    assert result["day_count"] == 0
    assert result["average_daily_kwh"] is None


@pytest.mark.asyncio
async def test_consumption_rejects_invalid_ranges_and_duplicate_dates() -> None:
    """Reject invalid requests and duplicate upstream observations."""
    client = AsyncMock()
    service = make_service(client)
    with pytest.raises(ValueError, match="date range"):
        await service.get_daily_consumption_statistics(date(2026, 10, 2), date(2026, 10, 1))
    client.meter_readings.return_value = SimpleNamespace(
        daily_consumption=[
            SimpleNamespace(date="2026-10-01", consumption_kwh=1.0),
            SimpleNamespace(date="2026-10-01", consumption_kwh=2.0),
        ]
    )
    with pytest.raises(ValueError, match="Duplicate"):
        await service.get_daily_consumption_statistics(date(2026, 10, 1), date(2026, 10, 2))


@pytest.mark.asyncio
async def test_consumption_requires_site_reference() -> None:
    """Fail before calling the upstream API when site reference is missing."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await make_service(client, site=None).get_daily_consumption_statistics(
            date(2026, 10, 1), date(2026, 10, 2)
        )
    client.meter_readings.assert_not_awaited()


@pytest.mark.asyncio
async def test_consumption_tool_registration() -> None:
    """FastMCP delegates the selected dates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_daily_consumption_statistics",
        {"start_date": "2026-10-01", "end_date": "2026-10-02"},
    )
    service.get_daily_consumption_statistics.assert_awaited_once_with(
        date(2026, 10, 1), date(2026, 10, 2)
    )
