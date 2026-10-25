"""Regression tests for duration-weighted price statistics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def _service(
    values: list[tuple[int, float]],
    *,
    start: datetime = datetime(2026, 6, 14, 22, tzinfo=UTC),
) -> FrankEnergieService:
    intervals = []
    cursor = start
    for minutes, value in values:
        end = cursor + timedelta(minutes=minutes)
        intervals.append(
            SimpleNamespace(date_from=cursor, date_till=end, total=value, per_unit="kWh")
        )
        cursor = end
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=intervals),
        gas=SimpleNamespace(price_data=[]),
    )
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))


@pytest.mark.asyncio
async def test_weighted_statistics_with_unequal_intervals() -> None:
    result = await _service([(15, -1.0), (45, 1.0)]).get_price_statistics(
        day=date(2026, 6, 15)
    )
    stats = result["electricity"]
    assert stats["interval_count"] == 2
    assert stats["coverage_status"] == "incomplete"
    assert stats["mean"] == pytest.approx(0.5)
    assert stats["variance"] == pytest.approx(0.75)
    assert stats["standard_deviation"] == pytest.approx(0.75**0.5)
    assert stats["median"] == 1.0
    assert stats["p10"] == -1.0
    assert stats["p25"] == -1.0
    assert stats["p75"] == 1.0
    assert stats["minimum"] == -1.0
    assert stats["maximum"] == 1.0
    assert stats["negative_interval_count"] == 1
    assert stats["negative_duration_seconds"] == 900
    assert result["gas"]["mean"] is None
    assert result["gas"]["coverage_status"] == "empty"


@pytest.mark.asyncio
async def test_complete_day_and_zero_prices() -> None:
    result = await _service([(60, 0.0)] * 24).get_price_statistics(
        day=date(2026, 6, 15), resolution="PT60M"
    )
    stats = result["electricity"]
    assert stats["complete"] is True
    assert stats["coverage_seconds"] == 86400
    assert stats["zero_interval_count"] == 24
    assert stats["zero_duration_seconds"] == 86400
    assert stats["standard_deviation"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("day", "hours"),
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)],
)
async def test_dst_day_coverage(day: date, hours: int) -> None:
    from zoneinfo import ZoneInfo

    local_start = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo("Europe/Amsterdam"))
    start = local_start.astimezone(UTC)
    result = await _service([(60, 0.2)] * hours, start=start).get_price_statistics(
        day=day, resolution="PT60M"
    )
    assert result["electricity"]["complete"] is True
    assert result["electricity"]["expected_seconds"] == hours * 3600


@pytest.mark.asyncio
async def test_rejects_overlapping_intervals() -> None:
    service = _service([(60, 0.1), (60, 0.2)])
    # A second interval with the same start violates the shared coverage contract.
    async with service.bridge.session() as client:
        data = client.prices.return_value.electricity.price_data
        data[1].date_from = data[0].date_from
    with pytest.raises(ValueError, match="Overlapping"):
        await service.get_price_statistics(day=date(2026, 6, 15))


@pytest.mark.asyncio
async def test_mcp_delegates_statistics() -> None:
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_price_statistics", {"day": "2026-06-15"})
    service.get_price_statistics.assert_awaited_once_with(
        day=date(2026, 6, 15), resolution="PT15M"
    )
