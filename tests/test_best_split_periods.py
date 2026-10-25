"""Regression tests for split-block price optimization."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _interval(start: datetime, value: float) -> SimpleNamespace:
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=15),
        total=value,
        per_unit="kWh",
    )


def _service(values: list[float | None]) -> FrankEnergieService:
    start = datetime(2026, 6, 14, 22, tzinfo=UTC)
    intervals = [
        _interval(start + timedelta(minutes=15 * index), value)
        for index, value in enumerate(values)
        if value is not None
    ]
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=intervals),
        gas=SimpleNamespace(price_data=[]),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))


@pytest.mark.asyncio
async def test_split_selects_global_optimum_without_overlaps() -> None:
    service = _service([1, 1, 9, 9, 1, 1])
    result = await service.get_best_split_periods(60, 30, date(2026, 6, 15))
    electricity = result["electricity"]
    assert electricity["status"] == "selected"
    assert electricity["average_total"] == 1
    assert electricity["total_cost_per_unit"] == 1
    assert len(electricity["blocks"]) == 2
    assert electricity["blocks"][0]["start"] != electricity["blocks"][1]["start"]
    assert result["gas"]["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_split_rejects_missing_bins_and_impossible_schedule() -> None:
    service = _service([1, None, 1])
    result = await service.get_best_split_periods(30, 30, date(2026, 6, 15))
    assert result["electricity"]["candidate_count"] == 0
    assert result["electricity"]["blocks"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("total,block", [(0, 15), (30, 0), (20, 15), (45, 30), (True, 15)])
async def test_split_rejects_invalid_durations(total: int, block: int) -> None:
    service = _service([])
    with pytest.raises(ValueError):
        await service.get_best_split_periods(total, block, date(2026, 6, 15))


@pytest.mark.asyncio
async def test_split_mcp_delegation() -> None:
    service = AsyncMock()
    server = create_server(service)
    arguments = {
        "total_duration_minutes": 60,
        "block_duration_minutes": 30,
        "day": "2026-06-15",
        "resolution": "PT15M",
    }
    await server.call_tool("get_best_split_periods", arguments)
    service.get_best_split_periods.assert_awaited_once_with(
        total_duration_minutes=60,
        block_duration_minutes=30,
        day=date(2026, 6, 15),
        resolution="PT15M",
    )
