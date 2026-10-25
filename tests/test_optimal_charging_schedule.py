"""Regression tests for optimal charging schedule planning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(prices: list[float]) -> FrankEnergieService:
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, price in enumerate(prices):
        begin = start + timedelta(hours=index)
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
async def test_split_schedule_uses_cheapest_slots() -> None:
    service = _service([0.5, -0.1, 0.3, 0.1])
    result = await service.get_optimal_charging_schedule(
        energy_kwh=2,
        max_power_kw=1,
        start=datetime(2026, 6, 14, 22, tzinfo=UTC),
        deadline=datetime(2026, 6, 15, 2, tzinfo=UTC),
        resolution="PT60M",
    )
    assert result["status"] == "ok"
    assert [slot["price_per_kwh"] for slot in result["schedule"]] == [-0.1, 0.1]
    assert result["estimated_cost"] == pytest.approx(0)


@pytest.mark.asyncio
async def test_contiguous_schedule_uses_cheapest_window() -> None:
    service = _service([0.1, 0.2, 0.9, -0.5])
    result = await service.get_optimal_charging_schedule(
        energy_kwh=2,
        max_power_kw=1,
        start=datetime(2026, 6, 14, 22, tzinfo=UTC),
        deadline=datetime(2026, 6, 15, 2, tzinfo=UTC),
        allow_interruptions=False,
        resolution="PT60M",
    )
    assert result["status"] == "ok"
    assert [slot["price_per_kwh"] for slot in result["schedule"]] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_incomplete_prices_are_not_filled() -> None:
    service = _service([0.1])
    result = await service.get_optimal_charging_schedule(
        energy_kwh=2,
        max_power_kw=1,
        start=datetime(2026, 6, 14, 22, tzinfo=UTC),
        deadline=datetime(2026, 6, 15, 1, tzinfo=UTC),
        resolution="PT60M",
    )
    assert result["status"] == "insufficient_prices"
    assert result["estimated_cost"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("energy", "power", "efficiency"),
    [(0, 1, 1), (1, 0, 1), (1, 1, 0), (1, 1, 1.1), (float("nan"), 1, 1)],
)
async def test_rejects_invalid_inputs(energy: float, power: float, efficiency: float) -> None:
    service = _service([])
    with pytest.raises(ValueError):
        await service.get_optimal_charging_schedule(
            energy_kwh=energy,
            max_power_kw=power,
            start=datetime(2026, 6, 14, 22, tzinfo=UTC),
            deadline=datetime(2026, 6, 15, 1, tzinfo=UTC),
            efficiency=efficiency,
            resolution="PT60M",
        )


@pytest.mark.asyncio
async def test_rejects_naive_times() -> None:
    service = _service([])
    with pytest.raises(ValueError, match="timezone-aware"):
        await service.get_optimal_charging_schedule(
            energy_kwh=1,
            max_power_kw=1,
            start=datetime(2026, 6, 15),
            deadline=datetime(2026, 6, 15, 2, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_mcp_delegates_charging_request() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_optimal_charging_schedule",
        {
            "energy_kwh": 2,
            "max_power_kw": 1,
            "start": "2026-06-15T00:00:00+00:00",
            "deadline": "2026-06-15T02:00:00+00:00",
            "resolution": "PT60M",
        },
    )
    assert service.get_optimal_charging_schedule.await_count == 1
