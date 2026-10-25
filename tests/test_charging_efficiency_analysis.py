"""Regression tests for charging efficiency comparisons."""

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
async def test_efficiency_changes_grid_energy_and_cost() -> None:
    service = _service([0.2, 0.2, 0.2, 0.2])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_efficiency_analysis(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadline=first + timedelta(hours=4),
        efficiencies=[1.0, 0.8],
        resolution="PT60M",
    )
    scenarios = result["efficiencies"]
    assert [item["efficiency"] for item in scenarios] == [1.0, 0.8]
    assert [item["required_grid_kwh"] for item in scenarios] == pytest.approx(
        [2.0, 2.5]
    )
    losses = [item["energy_loss_kwh"] for item in scenarios]
    assert losses == pytest.approx([0.0, 0.5])
    costs = [item["estimated_cost"] for item in scenarios]
    assert costs == pytest.approx([0.4, 0.5])
    assert scenarios[1]["additional_cost_vs_cheapest"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_missing_prices_do_not_invent_costs() -> None:
    service = _service([])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_efficiency_analysis(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadline=first + timedelta(hours=4),
        efficiencies=[0.9],
        resolution="PT60M",
    )
    assert result["lowest_estimated_cost"] is None
    assert result["efficiencies"][0]["status"] == "insufficient_prices"
    assert result["efficiencies"][0]["estimated_cost"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [[], [0], [-0.1], [1.1], [float("nan")], [1.0, 1.0], [True]],
)
async def test_rejects_invalid_efficiencies(values: list[float]) -> None:
    service = _service([])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    with pytest.raises(ValueError):
        await service.get_charging_efficiency_analysis(
            energy_kwh=2,
            max_power_kw=1,
            start=first,
            deadline=first + timedelta(hours=4),
            efficiencies=values,
        )


@pytest.mark.asyncio
async def test_mcp_delegates_to_service() -> None:
    service = AsyncMock()
    service.get_charging_efficiency_analysis.return_value = {"efficiencies": []}
    server = create_server(service)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    await server.call_tool(
        "get_charging_efficiency_analysis",
        {
            "energy_kwh": 2,
            "max_power_kw": 1,
            "start": first.isoformat(),
            "deadline": (first + timedelta(hours=4)).isoformat(),
            "efficiencies": [0.85, 0.95],
            "resolution": "PT60M",
        },
    )
    service.get_charging_efficiency_analysis.assert_awaited_once_with(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadline=first + timedelta(hours=4),
        efficiencies=[0.85, 0.95],
        allow_interruptions=True,
        resolution="PT60M",
    )
