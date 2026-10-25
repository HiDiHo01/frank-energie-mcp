"""Tests for consecutive-day all-in price summaries."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _series(start: datetime, values: list[float], minutes: int = 60) -> SimpleNamespace:
    entries = []
    for index, value in enumerate(values):
        begin = start + timedelta(minutes=index * minutes)
        entries.append(
            SimpleNamespace(
                date_from=begin,
                date_till=begin + timedelta(minutes=minutes),
                total=value,
                per_unit="kWh",
            )
        )
    return SimpleNamespace(price_data=entries)


def _service(today: list[float], tomorrow: list[float]) -> tuple[FrankEnergieService, AsyncMock]:
    client = AsyncMock()
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    second = first + timedelta(days=1)
    client.prices.side_effect = [
        SimpleNamespace(electricity=_series(first, today), gas=_series(first, [])),
        SimpleNamespace(electricity=_series(second, tomorrow), gas=_series(second, [])),
    ]
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    return service, client


@pytest.mark.asyncio
async def test_forecast_summary_extrema_and_comparison() -> None:
    service, client = _service([0.1, 0.3], [0.4, 0.2])
    result = await service.get_price_forecast_summary(day=date(2026, 6, 15), resolution="PT60M")
    electricity = result["electricity"]
    assert electricity["today"]["average_total"] == pytest.approx(0.2)
    assert electricity["tomorrow"]["average_total"] == pytest.approx(0.3)
    assert electricity["average_difference"] == pytest.approx(0.1)
    assert electricity["today"]["cheapest_period"]["average_total"] == 0.1
    assert electricity["today"]["dearest_period"]["average_total"] == 0.3
    assert electricity["tomorrow"]["cheapest_period"]["average_total"] == 0.2
    assert electricity["today"]["status"] == "incomplete"
    assert result["gas"]["today"]["status"] == "empty"
    assert client.prices.await_count == 2


@pytest.mark.asyncio
async def test_unavailable_tomorrow_has_no_invented_prices() -> None:
    service, _ = _service([0.1], [])
    result = await service.get_price_forecast_summary(
        day=date(2026, 6, 15), resolution="PT60M"
    )
    electricity = result["electricity"]
    assert electricity["tomorrow"]["status"] == "empty"
    assert electricity["tomorrow"]["cheapest_period"] is None
    assert electricity["average_difference"] is None


@pytest.mark.asyncio
async def test_window_requires_uninterrupted_prices() -> None:
    service, _ = _service([0.1], [])
    result = await service.get_price_forecast_summary(
        day=date(2026, 6, 15), resolution="PT60M", period_minutes=120
    )
    assert result["electricity"]["today"]["cheapest_period"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("period", [0, 30, 1501, True])
async def test_rejects_invalid_period(period: int) -> None:
    service, _ = _service([], [])
    with pytest.raises(ValueError, match="period_minutes"):
        await service.get_price_forecast_summary(
            day=date(2026, 6, 15), resolution="PT60M", period_minutes=period
        )


@pytest.mark.asyncio
async def test_mcp_delegation() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_price_forecast_summary",
        {"day": "2026-06-15", "resolution": "PT60M", "period_minutes": 120},
    )
    service.get_price_forecast_summary.assert_awaited_once_with(
        day=date(2026, 6, 15), resolution="PT60M", period_minutes=120
    )
