"""Regression tests for normalized price optimization."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.optimization import (
    battery_savings,
    best_start,
    energy_cost,
    split_periods,
    threshold_periods,
    validated_series,
)
from frank_energie_mcp.server import create_server

DAY = date(2026, 6, 15)
START = datetime(2026, 6, 14, 22, tzinfo=UTC)


def series(values: list[float], gap: int | None = None) -> list[tuple[datetime, datetime, float]]:
    """Generate normalized synthetic quarter-hour prices."""
    return [
        (
            START + timedelta(minutes=15 * (i + (1 if gap is not None and i >= gap else 0))),
            START + timedelta(minutes=15 * (i + 1 + (1 if gap is not None and i >= gap else 0))),
            value,
        )
        for i, value in enumerate(values)
    ]


def test_best_start_requires_consecutive_intervals() -> None:
    """Choose cheapest uninterrupted window and never bridge a missing bin."""
    assert best_start(series([5, 5, 1, 1]), 30, "PT15M")["average_total"] == 1
    assert best_start(series([1, 1, 1, 1], gap=2), 60, "PT15M") is None


def test_energy_cost_requires_full_coverage() -> None:
    """Calculate kWh times normalized price without inventing missing bins."""
    result = energy_cost(series([0.2, 0.4]), START, 30, 2, "PT15M")
    assert result["cost"] == pytest.approx(0.3)
    assert result["energy_kwh"] == 1
    assert energy_cost(series([0.2, 0.4], gap=1), START, 30, 2, "PT15M")["cost"] is None


def test_threshold_groups_and_split_selection() -> None:
    """Respect gaps and select nonoverlapping inexpensive blocks."""
    records = series([0.1, 0.1, 0.8, 0.1, 0.1])
    groups = threshold_periods(records, 0.2, True, 30)
    assert len(groups) == 2
    split = split_periods(records, 60, 30, "PT15M")
    assert split["status"] == "complete"
    assert len(split["periods"]) == 2
    assert split["average_total"] == pytest.approx(0.1)


def test_battery_requires_charge_before_discharge() -> None:
    """Battery estimate must respect chronological order and efficiency."""
    records = series([0.1] * 4 + [0.6] * 4)
    result = battery_savings(records, 1, 1, 1, 0.8, "PT15M")
    assert result["status"] == "estimated"
    assert result["cycle"]["estimated_savings"] > 0
    assert (
        battery_savings(series([0.6] * 4 + [0.1] * 4), 1, 1, 1, 0.8, "PT15M")["cycle"][
            "estimated_savings"
        ]
        <= 0
    )


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_battery_capacity(value: float) -> None:
    """Reject invalid numeric values rather than making misleading projections."""
    with pytest.raises(ValueError):
        battery_savings(series([0.1]), value, 1, 1, 0.9, "PT15M")


def test_validated_series_rejects_overlaps_and_outside_day() -> None:
    """Keep interval integrity validation independent of upstream ordering."""
    base = {
        "date_from": START.isoformat(),
        "date_till": (START + timedelta(minutes=15)).isoformat(),
        "total": 0.2,
    }
    assert len(validated_series([base], DAY, "PT15M")) == 1
    with pytest.raises(ValueError):
        validated_series([base, base], DAY, "PT15M")


@pytest.mark.asyncio
async def test_service_fetches_once_and_mcp_delegates() -> None:
    """Keep upstream usage bounded and expose the tool over FastMCP."""
    client = AsyncMock()
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=[
            SimpleNamespace(
                date_from=START,
                date_till=START + timedelta(minutes=15),
                total=0.1,
                per_unit="kWh",
            )
        ]),
        gas=SimpleNamespace(price_data=[]),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    result = await service.get_best_start_time(15, DAY)
    assert result["electricity"]["average_total"] == pytest.approx(0.1)
    assert result["gas"] is None
    client.prices.assert_awaited_once_with(DAY, resolution="PT15M")
    mock_service = AsyncMock()
    await create_server(mock_service).call_tool(
        "get_best_start_time", {"duration_minutes": 60, "day": "2026-06-15"}
    )
    mock_service.get_best_start_time.assert_awaited_once()
