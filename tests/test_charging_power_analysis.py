"""Regression tests for comparing charging power levels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(values: list[float]) -> FrankEnergieService:
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, price in enumerate(values):
        begin = first + timedelta(hours=index)
        entries.append(
            SimpleNamespace(
                date_from=begin,
                date_till=begin + timedelta(hours=1),
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
async def test_power_levels_compare_costs() -> None:
    service = _service([0.5, 0.3, 0.1, -0.2])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_power_analysis(
        energy_kwh=2,
        power_levels_kw=[1, 2],
        start=first,
        deadline=first + timedelta(hours=4),
        resolution="PT60M",
    )
    assert [item["power_kw"] for item in result["power_levels"]] == [1, 2]
    costs = [item["estimated_cost"] for item in result["power_levels"]]
    assert costs == pytest.approx([-0.1, -0.4])
    assert result["lowest_estimated_cost"] == pytest.approx(-0.4)
    difference = result["power_levels"][0]["additional_cost_vs_cheapest"]
    assert difference == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_missing_prices_have_no_savings() -> None:
    service = _service([])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_power_analysis(
        energy_kwh=2,
        power_levels_kw=[1],
        start=first,
        deadline=first + timedelta(hours=4),
        resolution="PT60M",
    )
    assert result["lowest_estimated_cost"] is None
    assert result["power_levels"][0]["status"] == "insufficient_prices"
    assert result["power_levels"][0]["additional_cost_vs_cheapest"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("levels", [[], [0], [-1], [float("nan")], [1, 1], [True]])
async def test_rejects_invalid_power_levels(levels: list[float]) -> None:
    service = _service([])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    with pytest.raises(ValueError):
        await service.get_charging_power_analysis(
            energy_kwh=2,
            power_levels_kw=levels,
            start=first,
            deadline=first + timedelta(hours=4),
        )


@pytest.mark.asyncio
async def test_mcp_delegates_to_service() -> None:
    service = AsyncMock()
    service.get_charging_power_analysis.return_value = {"power_levels": []}
    server = create_server(service)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    await server.call_tool(
        "get_charging_power_analysis",
        {
            "energy_kwh": 2,
            "power_levels_kw": [3.7, 7.4],
            "start": first.isoformat(),
            "deadline": (first + timedelta(hours=4)).isoformat(),
            "resolution": "PT60M",
        },
    )
    service.get_charging_power_analysis.assert_awaited_once_with(
        energy_kwh=2,
        power_levels_kw=[3.7, 7.4],
        start=first,
        deadline=first + timedelta(hours=4),
        efficiency=1.0,
        allow_interruptions=True,
        resolution="PT60M",
    )
