"""Regression tests for charging deadline comparisons."""

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
async def test_deadlines_compare_costs_without_inventing_prices() -> None:
    service = _service([0.5, 0.3, 0.1, -0.2])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_deadline_analysis(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadlines=[first + timedelta(hours=2), first + timedelta(hours=4)],
        resolution="PT60M",
    )
    costs = [item["estimated_cost"] for item in result["deadlines"]]
    assert costs == pytest.approx([0.8, -0.1])
    assert result["lowest_estimated_cost"] == pytest.approx(-0.1)
    assert result["deadlines"][0]["additional_cost_vs_cheapest"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_missing_prices_do_not_invent_savings() -> None:
    service = _service([])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_deadline_analysis(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadlines=[first + timedelta(hours=2)],
        resolution="PT60M",
    )
    assert result["lowest_estimated_cost"] is None
    assert result["deadlines"][0]["status"] == "insufficient_prices"
    assert result["deadlines"][0]["additional_cost_vs_cheapest"] is None


@pytest.mark.asyncio
async def test_rejects_duplicate_and_naive_deadlines() -> None:
    service = _service([])
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    with pytest.raises(ValueError, match="unique"):
        await service.get_charging_deadline_analysis(
            energy_kwh=1,
            max_power_kw=1,
            start=first,
            deadlines=[first + timedelta(hours=2)] * 2,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        await service.get_charging_deadline_analysis(
            energy_kwh=1,
            max_power_kw=1,
            start=first,
            deadlines=[datetime(2026, 6, 15, 2)],
        )


@pytest.mark.asyncio
async def test_mcp_tool_delegates() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_charging_deadline_analysis",
        {
            "energy_kwh": 2,
            "max_power_kw": 1,
            "start": "2026-06-14T22:00:00+00:00",
            "deadlines": ["2026-06-15T02:00:00+00:00"],
            "resolution": "PT60M",
        },
    )
    assert service.get_charging_deadline_analysis.await_count == 1
