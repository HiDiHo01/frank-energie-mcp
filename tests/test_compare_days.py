"""Regression tests for comparisons of normalized all-in prices."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _interval(start: datetime, total: float, minutes: int = 15) -> SimpleNamespace:
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=minutes),
        total=total,
        per_unit="kWh",
    )


@pytest.mark.asyncio
async def test_compare_days_differences_and_zero_baseline() -> None:
    client = AsyncMock()
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    end = datetime(2026, 6, 15, 22, tzinfo=UTC)
    client.prices.side_effect = [
        SimpleNamespace(
            electricity=SimpleNamespace(
                price_data=[_interval(start, 0.0), _interval(start + timedelta(minutes=15), 0.2)]
            ),
            gas=SimpleNamespace(price_data=[]),
        ),
        SimpleNamespace(
            electricity=SimpleNamespace(
                price_data=[_interval(end, 0.2), _interval(end + timedelta(minutes=15), 0.4)]
            ),
            gas=SimpleNamespace(price_data=[]),
        ),
    ]
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.compare_days(date(2026, 6, 15), date(2026, 6, 16))
    electricity = result["electricity"]
    assert electricity["first"]["minimum_total"] == 0.0
    assert electricity["second"]["maximum_total"] == pytest.approx(0.4)
    assert electricity["differences"]["average_total"]["absolute"] == pytest.approx(0.2)
    assert electricity["differences"]["average_total"]["percent"] == pytest.approx(200)
    assert electricity["differences"]["minimum_total"]["percent"] is None
    assert electricity["first"]["status"] == "incomplete"
    assert result["gas"]["differences"]["average_total"]["absolute"] is None


@pytest.mark.asyncio
async def test_compare_days_rejects_out_of_day_interval() -> None:
    client = AsyncMock()
    bad = _interval(datetime(2026, 6, 14, 21, tzinfo=UTC), 0.2)
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=[bad]),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    with pytest.raises(ValueError, match="outside"):
        await service.compare_days(date(2026, 6, 15), date(2026, 6, 16))


@pytest.mark.asyncio
async def test_compare_days_mcp_delegation() -> None:
    service = AsyncMock()
    server = create_server(service)
    arguments = {"first_day": "2026-06-15", "second_day": "2026-06-16", "resolution": "PT60M"}
    await server.call_tool("compare_days", arguments)
    service.compare_days.assert_awaited_once_with(
        first_day=date(2026, 6, 15),
        second_day=date(2026, 6, 16),
        resolution="PT60M",
    )
