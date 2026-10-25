"""Regression tests for daily normalized price volatility."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _interval(start: datetime, value: float) -> SimpleNamespace:
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=15),
        total=value,
        per_unit="kWh",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [[], [0.2], [0.1, 0.2, 0.3]])
async def test_volatility_metrics(values: list[float]) -> None:
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, value in enumerate(values):
        entries.append(_interval(start + timedelta(minutes=15 * index), value))
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=list(reversed(entries))),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.get_price_volatility(day=date(2026, 6, 15))
    electricity = result["electricity"]
    assert electricity["interval_count"] == len(values)
    assert electricity["status"] == ("empty" if not values else "incomplete")
    if not values:
        assert electricity["spread"] is None
        assert electricity["standard_deviation"] is None
        assert electricity["mean_absolute_change"] is None
    elif len(values) == 1:
        assert electricity["spread"] == 0
        assert electricity["standard_deviation"] == 0
        assert electricity["mean_absolute_change"] is None
    else:
        assert electricity["spread"] == pytest.approx(0.2)
        assert electricity["standard_deviation"] == pytest.approx(0.081649658)
        assert electricity["mean_absolute_change"] == pytest.approx(0.1)
        assert electricity["adjacent_pair_count"] == 2
    assert result["gas"]["status"] == "empty"


@pytest.mark.asyncio
async def test_volatility_does_not_bridge_missing_intervals() -> None:
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = [_interval(start, 0.1), _interval(start + timedelta(minutes=30), 0.5)]
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=entries),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.get_price_volatility(day=date(2026, 6, 15))
    assert result["electricity"]["adjacent_pair_count"] == 0
    assert result["electricity"]["mean_absolute_change"] is None


@pytest.mark.asyncio
async def test_volatility_mcp_delegation() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_price_volatility", {"day": "2026-06-15", "resolution": "PT60M"}
    )
    service.get_price_volatility.assert_awaited_once_with(
        day=date(2026, 6, 15), resolution="PT60M"
    )
