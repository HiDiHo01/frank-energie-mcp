"""Regression tests for charging start-time comparisons."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(values: list[float], minutes: int) -> FrankEnergieService:
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, price in enumerate(values):
        begin = first + timedelta(minutes=index * minutes)
        entries.append(
            SimpleNamespace(
                date_from=begin,
                date_till=begin + timedelta(minutes=minutes),
                total=price,
                per_unit="kWh",
            )
        )
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=entries),
        gas=SimpleNamespace(price_data=[]),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes,resolution", [(15, "PT15M"), (60, "PT60M")])
async def test_start_time_comparison(minutes: int, resolution: Literal["PT15M", "PT60M"]) -> None:
    service = _service([0.5, 0.3, 0.1, -0.2], minutes)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    step = timedelta(minutes=minutes)
    result = await service.get_charging_start_time_analysis(
        energy_kwh=2 * minutes / 60,
        max_power_kw=1,
        starts=[first, first + step * 2],
        deadline=first + step * 4,
        resolution=resolution,
    )
    expected_cost = -0.1 * minutes / 60
    assert [item["estimated_cost"] for item in result["starts"]] == pytest.approx(
        [expected_cost, expected_cost]
    )
    assert result["lowest_estimated_cost"] == pytest.approx(expected_cost)
    assert result["cheapest_start"] == first.isoformat()
    assert result["starts"][0]["charging_duration_minutes"] == 2 * minutes
    assert result["starts"][1]["savings_vs_most_expensive"] == pytest.approx(0)


@pytest.mark.asyncio
async def test_missing_prices_and_unachievable_start() -> None:
    service = _service([0.5, 0.3], 60)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_start_time_analysis(
        energy_kwh=2,
        max_power_kw=1,
        starts=[first, first + timedelta(hours=1)],
        deadline=first + timedelta(hours=2),
        resolution="PT60M",
    )
    assert result["starts"][0]["estimated_cost"] == pytest.approx(0.8)
    assert result["starts"][1]["status"] == "insufficient_prices"
    assert result["starts"][1]["charging_duration_minutes"] is None
    assert result["starts"][1]["savings_vs_most_expensive"] is None


@pytest.mark.asyncio
async def test_rejects_duplicate_and_naive_starts() -> None:
    service = _service([], 60)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    with pytest.raises(ValueError, match="unique"):
        await service.get_charging_start_time_analysis(
            energy_kwh=1,
            max_power_kw=1,
            starts=[first, first],
            deadline=first + timedelta(hours=2),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        await service.get_charging_start_time_analysis(
            energy_kwh=1,
            max_power_kw=1,
            starts=[datetime(2026, 6, 15, 2)],
            deadline=first + timedelta(hours=4),
        )


@pytest.mark.asyncio
async def test_mcp_tool_delegates() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_charging_start_time_analysis",
        {
            "energy_kwh": 2,
            "max_power_kw": 1,
            "starts": ["2026-06-14T22:00:00+00:00"],
            "deadline": "2026-06-15T02:00:00+00:00",
            "resolution": "PT60M",
        },
    )
    assert service.get_charging_start_time_analysis.await_count == 1
