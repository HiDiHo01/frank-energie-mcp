"""Charging strategy comparison regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(values: list[float]) -> FrankEnergieService:
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, price in enumerate(values):
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
async def test_compare_three_strategies_and_savings() -> None:
    service = _service([0.5, 0.1, 0.4, -0.2])
    result = await service.compare_charging_strategies(
        energy_kwh=2,
        max_power_kw=1,
        start=datetime(2026, 6, 14, 22, tzinfo=UTC),
        deadline=datetime(2026, 6, 15, 2, tzinfo=UTC),
        resolution="PT60M",
    )
    plans = result["strategies"]
    assert plans["immediate"]["estimated_cost"] == pytest.approx(0.6)
    assert plans["cheapest_contiguous"]["estimated_cost"] == pytest.approx(0.2)
    assert plans["cheapest_interruptible"]["estimated_cost"] == pytest.approx(-0.1)
    assert result["savings_vs_immediate"]["cheapest_interruptible"][
        "saving_amount"
    ] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_missing_prices_do_not_invent_savings() -> None:
    service = _service([])
    result = await service.compare_charging_strategies(
        energy_kwh=2,
        max_power_kw=1,
        start=datetime(2026, 6, 14, 22, tzinfo=UTC),
        deadline=datetime(2026, 6, 15, 2, tzinfo=UTC),
        resolution="PT60M",
    )
    assert all(
        plan["status"] == "insufficient_prices"
        for plan in result["strategies"].values()
    )
    assert all(
        comparison["saving_amount"] is None
        for comparison in result["savings_vs_immediate"].values()
    )


@pytest.mark.asyncio
async def test_immediate_does_not_fit_before_deadline() -> None:
    service = _service([0.1, 0.2])
    result = await service.compare_charging_strategies(
        energy_kwh=3,
        max_power_kw=1,
        start=datetime(2026, 6, 14, 22, tzinfo=UTC),
        deadline=datetime(2026, 6, 15, 0, tzinfo=UTC),
        resolution="PT60M",
    )
    assert result["strategies"]["immediate"]["status"] == "insufficient_prices"


@pytest.mark.asyncio
async def test_mcp_tool_delegates() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "compare_charging_strategies",
        {
            "energy_kwh": 2,
            "max_power_kw": 1,
            "start": "2026-06-14T22:00:00+00:00",
            "deadline": "2026-06-15T02:00:00+00:00",
            "resolution": "PT60M",
        },
    )
    assert service.compare_charging_strategies.await_count == 1
