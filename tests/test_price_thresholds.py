"""Price threshold grouping contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _record(start: datetime, minutes: int, total: float) -> SimpleNamespace:
    """Build a synthetic upstream price interval."""
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=minutes),
        total=total,
        per_unit="kWh",
    )


def _service(entries: list[SimpleNamespace]) -> tuple[FrankEnergieService, AsyncMock]:
    """Provide a network-free service."""
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=entries),
        gas=SimpleNamespace(price_data=[]),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client)), client


@pytest.mark.asyncio
@pytest.mark.parametrize("step,resolution", [(15, "PT15M"), (60, "PT60M")])
async def test_threshold_groups_adjacent_prices_and_splits_gaps(step: int, resolution: str) -> None:
    """Matching bins separated by a gap remain distinct periods."""
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    service, client = _service(
        [
            _record(start + timedelta(minutes=i * step), step, price)
            for i, price in [(0, -0.1), (1, 0.1), (3, 0.1), (4, 0.3)]
        ]
    )
    result = await service.get_price_threshold_periods(0.2, "below", date(2026, 6, 15), resolution)
    periods = result["electricity"]["periods"]
    assert len(periods) == 2
    assert periods[0]["interval_count"] == 2
    assert periods[0]["average_total"] == pytest.approx(0.0)
    assert periods[1]["interval_count"] == 1
    assert result["electricity"]["matching_interval_count"] == 3
    assert result["electricity"]["status"] == "incomplete"
    client.prices.assert_awaited_once_with(date(2026, 6, 15), resolution=resolution)


@pytest.mark.asyncio
async def test_above_comparison_is_strict() -> None:
    """Threshold equality is excluded and negative prices remain valid."""
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    service, _ = _service(
        [_record(start, 15, -0.2), _record(start + timedelta(minutes=15), 15, -0.1)]
    )
    result = await service.get_price_threshold_periods(-0.2, "above", date(2026, 6, 15))
    assert result["electricity"]["matching_interval_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), True])
async def test_invalid_threshold_rejected_before_network(threshold: float) -> None:
    """Do not call upstream for invalid numeric input."""
    service, client = _service([])
    with pytest.raises(ValueError, match="threshold"):
        await service.get_price_threshold_periods(threshold)
    client.prices.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_comparison_rejected_before_network() -> None:
    """Only below and above comparisons are accepted."""
    service, client = _service([])
    with pytest.raises(ValueError, match="comparison"):
        await service.get_price_threshold_periods(0.2, "equal")  # type: ignore[arg-type]
    client.prices.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_threshold_delegates() -> None:
    """FastMCP forwards typed threshold arguments."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_price_threshold_periods",
        {"threshold": 0.2, "comparison": "above", "day": "2026-06-15", "resolution": "PT60M"},
    )
    service.get_price_threshold_periods.assert_awaited_once_with(
        threshold=0.2, comparison="above", day=date(2026, 6, 15), resolution="PT60M"
    )


@pytest.mark.asyncio
async def test_dst_fallback_keeps_repeated_hour_contiguous() -> None:
    """UTC-adjacent bins across the Amsterdam clock rollback form one group."""
    start = datetime(2026, 10, 24, 22, tzinfo=UTC)
    service, _ = _service([_record(start + timedelta(hours=i), 60, 0.1) for i in range(5)])
    result = await service.get_price_threshold_periods(
        0.2, day=date(2026, 10, 25), resolution="PT60M"
    )
    assert result["electricity"]["periods"][0]["duration_minutes"] == 300
