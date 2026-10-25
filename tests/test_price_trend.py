"""Contract tests for normalized daily price trends."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _record(start: datetime, minutes: int, total: float) -> SimpleNamespace:
    """Construct a normalized-compatible upstream interval."""
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=minutes),
        total=total,
        per_unit="kWh",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prices", "expected", "change"),
    [
        ([0.1, 0.3], "rising", 0.2),
        ([0.3, 0.1], "falling", -0.2),
        ([0.2, 0.2], "stable", 0.0),
        ([0.2], "unknown", None),
        ([], "unknown", None),
    ],
)
async def test_price_trend_directions(
    prices: list[float], expected: str, change: float | None
) -> None:
    """A daily trend compares the first and last chronological total prices."""
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    entries = []
    for index, price in enumerate(prices):
        interval_start = start + timedelta(minutes=index * 15)
        entries.append(_record(interval_start, 15, price))
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=list(reversed(entries))),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.get_price_trend(day=date(2026, 6, 15))

    assert result["electricity"]["trend"] == expected
    if change is None:
        assert result["electricity"]["change_total"] is None
    else:
        assert result["electricity"]["change_total"] == pytest.approx(change)
    assert result["gas"]["trend"] == "unknown"
    assert result["electricity"]["interval_count"] == len(prices)


@pytest.mark.asyncio
async def test_price_trend_mcp_delegates() -> None:
    """The public tool forwards date and supported resolution."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_price_trend", {"day": "2026-06-15", "resolution": "PT60M"})
    service.get_price_trend.assert_awaited_once_with(day=date(2026, 6, 15), resolution="PT60M")
