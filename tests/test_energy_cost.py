"""Electricity cost estimation contracts for complete and partial price windows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _record(start: datetime, minutes: int, total: float) -> SimpleNamespace:
    """Create an upstream electricity price interval."""
    return SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=minutes),
        total=total,
        per_unit="kWh",
    )


def _service(entries: list[SimpleNamespace]) -> tuple[FrankEnergieService, AsyncMock]:
    """Provide a mocked upstream client."""
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=entries),
        gas=SimpleNamespace(price_data=[]),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client)), client


@pytest.mark.asyncio
@pytest.mark.parametrize("step", [15, 60])
async def test_cost_weights_partial_intervals_by_elapsed_seconds(step: int) -> None:
    """A fixed consumption rate uses duration-weighted normalized prices."""
    start = datetime(2026, 6, 15, 0, tzinfo=UTC)
    entries = [_record(start, step, 0.1), _record(start + timedelta(minutes=step), step, 0.3)]
    service, client = _service(entries)
    result = await service.calculate_energy_cost(
        start + timedelta(seconds=step * 30),
        start + timedelta(seconds=step * 90),
        2.0,
        "PT15M" if step == 15 else "PT60M",
    )
    assert result["average_total"] == pytest.approx(0.2)
    assert result["estimated_cost"] == pytest.approx(0.4)
    assert result["duration_seconds"] == step * 60
    assert client.prices.await_count == 1


@pytest.mark.asyncio
async def test_missing_price_coverage_fails_closed() -> None:
    """A missing interval must not produce an understated cost."""
    start = datetime(2026, 6, 15, 0, tzinfo=UTC)
    service, _ = _service([_record(start, 15, 0.1)])
    with pytest.raises(ValueError, match="cover"):
        await service.calculate_energy_cost(start, start + timedelta(minutes=30), 2.0)


@pytest.mark.asyncio
async def test_overlapping_intervals_are_rejected() -> None:
    """Duplicate intervals cannot be counted twice."""
    start = datetime(2026, 6, 15, 0, tzinfo=UTC)
    service, _ = _service([_record(start, 15, 0.1), _record(start, 15, 0.2)])
    with pytest.raises(ValueError, match="overlaps"):
        await service.calculate_energy_cost(start, start + timedelta(minutes=15), 1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), True])
async def test_invalid_consumption_rejected_before_network(value: float) -> None:
    """Only finite non-negative quantities are accepted."""
    service, client = _service([])
    start = datetime(2026, 6, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="consumption_kwh"):
        await service.calculate_energy_cost(start, start + timedelta(hours=1), value)
    client.prices.assert_not_awaited()


@pytest.mark.asyncio
async def test_naive_and_reversed_dates_rejected() -> None:
    """Time inputs must identify an unambiguous positive-duration interval."""
    service, client = _service([])
    start = datetime(2026, 6, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone-aware"):
        await service.calculate_energy_cost(start.replace(tzinfo=None), start, 1.0)
    with pytest.raises(ValueError, match="later"):
        await service.calculate_energy_cost(start, start, 1.0)
    client.prices.assert_not_awaited()


@pytest.mark.asyncio
async def test_dst_fall_back_crosses_two_local_dates_without_naive_math() -> None:
    """Autumn repeated local hour remains distinct in UTC."""
    tz = ZoneInfo("Europe/Amsterdam")
    start = datetime(2026, 10, 25, 0, tzinfo=UTC)
    entries = [_record(start + timedelta(hours=i), 60, 0.1) for i in range(3)]
    service, client = _service(entries)
    result = await service.calculate_energy_cost(
        start.astimezone(tz), (start + timedelta(hours=3)).astimezone(tz), 3.0, "PT60M"
    )
    assert result["duration_seconds"] == 10800
    assert result["estimated_cost"] == pytest.approx(0.3)
    assert client.prices.await_count == 1


@pytest.mark.asyncio
async def test_mcp_cost_tool_delegates() -> None:
    """FastMCP parses timezone-aware datetime parameters."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "calculate_energy_cost",
        {
            "start": "2026-06-15T00:00:00+00:00",
            "end": "2026-06-15T01:00:00+00:00",
            "consumption_kwh": 2.0,
            "resolution": "PT60M",
        },
    )
    service.calculate_energy_cost.assert_awaited_once_with(
        start=datetime(2026, 6, 15, tzinfo=UTC),
        end=datetime(2026, 6, 15, 1, tzinfo=UTC),
        consumption_kwh=2.0,
        resolution="PT60M",
    )
