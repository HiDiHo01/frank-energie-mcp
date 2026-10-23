"""Contiguous daily price-window selection contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
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
    resolution: Literal["PT15M", "PT60M"], step: int
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
