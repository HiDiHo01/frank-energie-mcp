"""Regression tests for conservative single-cycle battery savings."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(prices: list[float], *, step: int = 15) -> FrankEnergieService:
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    intervals = [
        SimpleNamespace(
            date_from=start + timedelta(minutes=index * step),
            date_till=start + timedelta(minutes=(index + 1) * step),
            total=price,
            per_unit="kWh",
        )
        for index, price in enumerate(prices)
    ]
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=intervals),
        gas=SimpleNamespace(price_data=[]),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))


@pytest.mark.asyncio
async def test_battery_savings_finds_profitable_cycle_with_losses() -> None:
    prices = [0.2] * 96
    prices[0] = -0.1
    prices[1] = 0.8
    service = _service(prices)
    result = await service.calculate_battery_savings(
        capacity_kwh=1.0,
        charge_power_kw=4.0,
        discharge_power_kw=4.0,
        charge_efficiency=0.9,
        discharge_efficiency=0.9,
        day=date(2026, 6, 15),
    )
    assert result["coverage_status"] == "complete"
    assert result["estimated_savings"] > 0
    cycle = result["best_cycle"]
    assert cycle is not None
    assert cycle["grid_input_kwh"] <= 1.0
    assert cycle["delivered_kwh"] <= 1.0
    assert cycle["charge_start"] < cycle["discharge_start"]


@pytest.mark.asyncio
async def test_battery_savings_incomplete_data_does_not_guess() -> None:
    service = _service([0.1, 0.8])
    result = await service.calculate_battery_savings(1.0, 4.0, 4.0)
    assert result["coverage_status"] == "incomplete"
    assert result["estimated_savings"] is None
    assert result["best_cycle"] is None


@pytest.mark.asyncio
async def test_battery_savings_no_profitable_cycle() -> None:
    service = _service([0.0] * 96)
    result = await service.calculate_battery_savings(1.0, 4.0, 4.0)
    assert result["estimated_savings"] == 0
    assert result["best_cycle"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"capacity_kwh": 0.0},
        {"charge_power_kw": -1.0},
        {"discharge_power_kw": float("nan")},
        {"charge_efficiency": 1.1},
        {"discharge_efficiency": 0.0},
        {"capacity_kwh": True},
    ],
)
async def test_battery_savings_rejects_invalid_inputs(kwargs: dict[str, float]) -> None:
    options = {"capacity_kwh": 1.0, "charge_power_kw": 4.0, "discharge_power_kw": 4.0}
    options.update(kwargs)
    with pytest.raises(ValueError):
        await _service([]).calculate_battery_savings(
            capacity_kwh=options["capacity_kwh"],
            charge_power_kw=options["charge_power_kw"],
            discharge_power_kw=options["discharge_power_kw"],
            charge_efficiency=options.get("charge_efficiency", 0.95),
            discharge_efficiency=options.get("discharge_efficiency", 0.95),
        )


@pytest.mark.asyncio
async def test_battery_savings_mcp_delegation() -> None:
    service = AsyncMock()
    server = create_server(service)
    arguments = {
        "capacity_kwh": 1.0,
        "charge_power_kw": 4.0,
        "discharge_power_kw": 4.0,
        "day": "2026-06-15",
    }
    await server.call_tool("calculate_battery_savings", arguments)
    service.calculate_battery_savings.assert_awaited_once_with(
        capacity_kwh=1.0,
        charge_power_kw=4.0,
        discharge_power_kw=4.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        day=date(2026, 6, 15),
        resolution="PT15M",
    )
