"""Daily average-price contracts, including incomplete and DST days."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server

AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def _interval(start: datetime, minutes: int, total: float) -> SimpleNamespace:
    """Create a synthetic upstream price interval."""
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=minutes),
        total=total,
        per_unit="kWh",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("day", "hours"),
    [(date(2026, 3, 29), 23), (date(2026, 6, 15), 24), (date(2026, 10, 25), 25)],
)
async def test_average_covers_dst_calendar_days(day: date, hours: int) -> None:
    """Use actual Amsterdam day duration and all available interval totals."""
    start = datetime(day.year, day.month, day.day, tzinfo=AMSTERDAM).astimezone(UTC)
    electricity = [
        _interval(start + timedelta(minutes=i * 15), 15, 0.2 + (i % 2) * 0.2)
        for i in range(hours * 4)
    ]
    gas = [_interval(start, 60, 1.5)]
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=electricity),
        gas=SimpleNamespace(price_data=gas),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))

    result = await service.get_average_prices(day, resolution="PT15M")

    assert result["electricity"]["average_total"] == pytest.approx(0.3)
    assert result["electricity"]["interval_count"] == hours * 4
    assert result["electricity"]["coverage_seconds"] == hours * 3600
    assert result["electricity"]["complete"] is True
    assert result["gas"]["average_total"] == 1.5
    assert result["gas"]["status"] == "incomplete"
    client.prices.assert_awaited_once_with(day, resolution="PT15M")
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_and_gapped_series() -> None:
    """Do not fabricate missing prices or count gaps as covered time."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(
            price_data=[
                _interval(start, 15, 0.1),
                _interval(start + timedelta(minutes=30), 15, 0.3),
            ]
        ),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.get_average_prices(day, resolution="PT60M")
    assert result["electricity"]["average_total"] == pytest.approx(0.2)
    assert result["electricity"]["coverage_seconds"] == 1800
    assert result["electricity"]["status"] == "incomplete"
    assert result["gas"]["average_total"] is None
    assert result["gas"]["interval_count"] == 0
    assert result["gas"]["first_interval"] is None
    assert result["gas"]["last_interval"] is None
    assert result["gas"]["status"] == "empty"


@pytest.mark.asyncio
async def test_overlapping_intervals_rejected() -> None:
    """Prevent double-counting overlapping or duplicate intervals."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(
            price_data=[
                _interval(start, 30, 0.1),
                _interval(start + timedelta(minutes=15), 30, 0.3),
            ]
        ),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    with pytest.raises(ValueError, match="Overlapping"):
        await service.get_average_prices(day)


@pytest.mark.asyncio
async def test_mcp_tool_delegates_date_and_resolution() -> None:
    """Verify the registered MCP tool passes both arguments to the service."""
    service = AsyncMock()
    service.get_average_prices.return_value = {
        "date": "2026-06-15",
        "resolution": "PT60M",
        "electricity": {},
        "gas": {},
    }
    server = create_server(service)
    await server.call_tool("get_average_prices", {"day": "2026-06-15", "resolution": "PT60M"})
    service.get_average_prices.assert_awaited_once_with(day=date(2026, 6, 15), resolution="PT60M")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "expected_total"),
    [("get_lowest_price", -0.1), ("get_highest_price", 0.4)],
)
async def test_extreme_price_tools(method: str, expected_total: float) -> None:
    """Choose min/max normalized totals, including negative electricity prices."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(
            price_data=[
                _interval(start, 15, 0.4),
                _interval(start + timedelta(minutes=15), 15, -0.1),
                _interval(start + timedelta(minutes=30), 15, 0.2),
            ]
        ),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await getattr(service, method)(day=day, resolution="PT15M")
    assert result["electricity"]["price"]["total"] == expected_total
    assert result["electricity"]["interval_count"] == 3
    assert result["electricity"]["status"] == "incomplete"
    assert result["gas"]["price"] is None
    assert result["gas"]["status"] == "empty"
    client.prices.assert_awaited_once_with(day, resolution="PT15M")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_lowest_price", "get_highest_price"])
async def test_extreme_price_mcp_delegation(method: str) -> None:
    """Forward the selected day and resolution through the MCP tool."""
    service = AsyncMock()
    getattr(service, method).return_value = {"electricity": {}, "gas": {}}
    server = create_server(service)
    await server.call_tool(method, {"day": "2026-06-15", "resolution": "PT60M"})
    getattr(service, method).assert_awaited_once_with(day=date(2026, 6, 15), resolution="PT60M")
