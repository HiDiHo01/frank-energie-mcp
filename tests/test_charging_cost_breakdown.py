"""Regression tests for optimal charging cost breakdown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(prices: list[float], minutes: int) -> FrankEnergieService:
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, price in enumerate(prices):
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
@pytest.mark.parametrize(
    "minutes,resolution",
    [(15, "PT15M"), (60, "PT60M")],
)
async def test_breakdown_with_negative_prices_and_losses(
    minutes: int, resolution: Literal["PT15M", "PT60M"]
) -> None:
    service = _service([-0.2, 0.1, 0.3, 0.4], minutes)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_cost_breakdown(
        energy_kwh=1,
        max_power_kw=4 if minutes == 15 else 1,
        start=first,
        deadline=first + timedelta(minutes=4 * minutes),
        efficiency=0.5,
        resolution=resolution,
    )
    assert result["status"] == "ok"
    assert result["required_grid_kwh"] == pytest.approx(2)
    assert result["energy_loss_kwh"] == pytest.approx(1)
    assert result["total_charging_minutes"] == 2 * minutes
    assert result["negative_price_grid_kwh"] == pytest.approx(1)
    assert result["negative_price_cost"] == pytest.approx(-0.2)
    assert result["estimated_cost"] == pytest.approx(-0.1)
    assert result["average_price_per_grid_kwh"] == pytest.approx(-0.05)
    assert len(result["schedule"]) == 2


@pytest.mark.asyncio
async def test_missing_prices_do_not_invent_costs() -> None:
    service = _service([], 60)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    result = await service.get_charging_cost_breakdown(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadline=first + timedelta(hours=4),
        resolution="PT60M",
    )
    assert result["status"] == "insufficient_prices"
    assert result["estimated_cost"] is None
    assert result["average_price_per_grid_kwh"] is None
    assert result["negative_price_cost"] is None
    assert result["total_charging_minutes"] is None


@pytest.mark.asyncio
async def test_mcp_delegates_to_service() -> None:
    service = AsyncMock()
    service.get_charging_cost_breakdown.return_value = {"status": "ok"}
    server = create_server(service)
    first = datetime(2026, 6, 14, 22, tzinfo=UTC)
    await server.call_tool(
        "get_charging_cost_breakdown",
        {
            "energy_kwh": 2,
            "max_power_kw": 1,
            "start": first.isoformat(),
            "deadline": (first + timedelta(hours=4)).isoformat(),
            "resolution": "PT60M",
        },
    )
    service.get_charging_cost_breakdown.assert_awaited_once_with(
        energy_kwh=2,
        max_power_kw=1,
        start=first,
        deadline=first + timedelta(hours=4),
        efficiency=1.0,
        allow_interruptions=True,
        resolution="PT60M",
    )
