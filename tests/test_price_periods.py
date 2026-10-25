"""Contiguous daily price-window selection contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import (
    FrankEnergieLibraryBridge,
    FrankEnergieService,
    PriceResolution,
)
from frank_energie_mcp.server import create_server


def _record(start: datetime, minutes: int, total: float) -> SimpleNamespace:
    """Make a synthetic upstream interval."""
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=minutes),
        total=total,
        per_unit="kWh",
    )


def _service(
    electricity: list[SimpleNamespace], gas: list[SimpleNamespace] | None = None
) -> tuple[FrankEnergieService, AsyncMock]:
    """Provide an upstream response without network access."""
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=electricity),
        gas=SimpleNamespace(price_data=gas if gas is not None else []),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client)), client


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution,step", [("PT15M", 15), ("PT60M", 60)])
async def test_cheapest_and_most_expensive_four_hours(
    resolution: PriceResolution, step: int
) -> None:
    """Choose a four-hour consecutive window by mean price, not a single interval."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    per_hour = 60 // step
    entries = [
        _record(start + timedelta(minutes=i * step), step, 0.1 if i < 4 * per_hour else 0.5)
        for i in range(8 * per_hour)
    ]
    service, client = _service(entries)
    low = await service.get_lowest_period(240, day, resolution=resolution)
    high = await service.get_highest_period(240, day, resolution=resolution)
    assert low["electricity"]["period"]["average_total"] == pytest.approx(0.1)
    assert high["electricity"]["period"]["average_total"] == pytest.approx(0.5)
    assert low["electricity"]["period"]["interval_count"] == 240 // step
    assert datetime.fromisoformat(low["electricity"]["period"]["start"]) == entries[0].date_from
    assert (
        datetime.fromisoformat(high["electricity"]["period"]["start"])
        == entries[4 * per_hour].date_from
    )
    assert low["gas"]["period"] is None
    assert client.prices.await_count == 2


@pytest.mark.asyncio
async def test_gap_cannot_form_consecutive_window() -> None:
    """Never bridge a missing interval to manufacture a complete period."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = [_record(start + timedelta(minutes=i * 15), 15, 0.1) for i in (0, 1, 3, 4)]
    service, _ = _service(entries)
    result = await service.get_lowest_period(60, day)
    assert result["electricity"]["period"] is None
    assert result["electricity"]["status"] == "incomplete"


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, -15, 17, 30])
async def test_invalid_hourly_period_rejected(minutes: int) -> None:
    """Hourly windows require positive multiples of 60 minutes."""
    service, client = _service([])
    with pytest.raises(ValueError, match="positive multiple"):
        await service.get_highest_period(minutes, date(2026, 6, 15), "PT60M")
    client.prices.assert_not_awaited()


@pytest.mark.asyncio
async def test_period_tools_delegate_through_mcp() -> None:
    """Validate period size, date and resolution delegation."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_lowest_period",
        {"period_minutes": 240, "day": "2026-06-15", "resolution": "PT15M"},
    )
    service.get_lowest_period.assert_awaited_once_with(
        period_minutes=240, day=date(2026, 6, 15), resolution="PT15M"
    )
    await server.call_tool(
        "get_highest_period",
        {"period_minutes": 240, "day": "2026-06-15", "resolution": "PT60M"},
    )
    service.get_highest_period.assert_awaited_once_with(
        period_minutes=240, day=date(2026, 6, 15), resolution="PT60M"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution,step", [("PT15M", 15), ("PT60M", 60)])
async def test_best_start_time_reuses_cheapest_electricity_window(
    resolution: PriceResolution, step: int
) -> None:
    """Select the cheapest complete window and estimate a constant-load cost."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = [
        _record(start + timedelta(minutes=i * step), step, 0.5 if i < 60 // step else 0.1)
        for i in range(120 // step)
    ]
    service, client = _service(entries)
    result = await service.get_best_start_time(60, day, resolution, consumption_kwh=2.0)
    assert datetime.fromisoformat(result["start"]) == start + timedelta(hours=1)
    assert datetime.fromisoformat(result["end"]) == start + timedelta(hours=2)
    assert result["average_total"] == pytest.approx(0.1)
    assert result["estimated_cost"] == pytest.approx(0.2)
    assert result["consumption_kwh"] == 2.0
    client.prices.assert_awaited_once_with(day, resolution=resolution)


@pytest.mark.asyncio
async def test_best_start_time_missing_window_and_cost() -> None:
    """A gap must not produce a fabricated start or estimated cost."""
    day = date(2026, 6, 15)
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    service, _ = _service([_record(start, 15, 0.1)])
    result = await service.get_best_start_time(60, day, consumption_kwh=3.0)
    assert result["start"] is None
    assert result["end"] is None
    assert result["estimated_cost"] is None
    assert result["status"] == "incomplete"


@pytest.mark.asyncio
@pytest.mark.parametrize("consumption", [-1.0, float("nan"), float("inf"), True])
async def test_best_start_time_rejects_invalid_consumption(consumption: float) -> None:
    """Reject invalid energy quantities before contacting upstream."""
    service, client = _service([])
    with pytest.raises(ValueError, match="consumption_kwh"):
        await service.get_best_start_time(60, consumption_kwh=consumption)
    client.prices.assert_not_awaited()


@pytest.mark.asyncio
async def test_best_start_time_mcp_delegation() -> None:
    """MCP exposes the new tool with validated date and resolution."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_best_start_time",
        {
            "period_minutes": 60,
            "day": "2026-06-15",
            "resolution": "PT60M",
            "consumption_kwh": 2.5,
        },
    )
    service.get_best_start_time.assert_awaited_once_with(
        period_minutes=60,
        day=date(2026, 6, 15),
        resolution="PT60M",
        consumption_kwh=2.5,
    )
