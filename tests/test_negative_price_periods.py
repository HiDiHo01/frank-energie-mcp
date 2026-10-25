"""Regression tests for the negative-price MCP shortcut."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["PT15M", "PT60M"])
async def test_negative_price_periods_reuses_threshold_analysis(resolution: str) -> None:
    """Delegate to the existing strict negative-threshold implementation."""
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=AsyncMock))
    service.get_price_threshold_periods = AsyncMock(return_value={"electricity": {"periods": []}})
    day = date(2026, 10, 25)

    result = await service.get_negative_price_periods(day=day, resolution=resolution)

    assert result["electricity"]["periods"] == []
    service.get_price_threshold_periods.assert_awaited_once_with(
        threshold=0.0, comparison="below", day=day, resolution=resolution
    )


@pytest.mark.asyncio
async def test_negative_price_periods_excludes_zero_and_keeps_gaps() -> None:
    """Strictly negative, consecutive prices form periods; zero and gaps split them."""
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)

    def record(offset: int, price: float) -> SimpleNamespace:
        return SimpleNamespace(
            date_from=start + timedelta(minutes=offset),
            date_till=start + timedelta(minutes=offset + 15),
            total=price,
            per_unit="kWh",
        )

    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(
            price_data=[
                record(0, -0.2),
                record(15, -0.1),
                record(30, 0.0),
                record(45, -0.1),
                record(75, -0.3),
            ]
        ),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.get_negative_price_periods(day=date(2026, 6, 15))

    periods = result["electricity"]["periods"]
    assert [period["interval_count"] for period in periods] == [2, 1, 1]
    assert result["electricity"]["matching_interval_count"] == 4
    assert result["gas"]["periods"] == []


@pytest.mark.asyncio
async def test_negative_price_periods_mcp_delegates() -> None:
    """The FastMCP entry point forwards date and resolution to the service."""
    service = AsyncMock()
    server = create_server(service)

    await server.call_tool(
        "get_negative_price_periods",
        {"day": "2026-10-25", "resolution": "PT60M"},
    )

    service.get_negative_price_periods.assert_awaited_once_with(
        day=date(2026, 10, 25), resolution="PT60M"
    )
