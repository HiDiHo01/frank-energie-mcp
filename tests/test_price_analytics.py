"""Regression tests for daily price analytics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from frank_energie_mcp.optimization import (
    price_statistics,
    price_trend,
    price_volatility,
    threshold_periods,
)

START = datetime(2026, 6, 14, 22, tzinfo=UTC)


def series(values: list[float]) -> list[tuple[datetime, datetime, float]]:
    """Create ordered, adjacent synthetic quarter-hour price intervals."""
    return [
        (
            START + timedelta(minutes=15 * index),
            START + timedelta(minutes=15 * (index + 1)),
            value,
        )
        for index, value in enumerate(values)
    ]


def test_statistics_and_population_volatility() -> None:
    """Compute exact median, quartiles and population standard deviation."""
    stats = price_statistics(series([1, 2, 3, 4]))
    assert stats["count"] == 4
    assert stats["mean"] == 2.5
    assert stats["median"] == 2.5
    assert stats["p25"] == pytest.approx(1.75)
    assert stats["p75"] == pytest.approx(3.25)
    assert stats["standard_deviation"] == pytest.approx(1.11803398875)
    volatility = price_volatility(series([1, 2, 3, 4]))
    assert volatility["largest_increase"] == 1
    assert volatility["mean_absolute_change"] == 1


def test_empty_and_single_price_series() -> None:
    """Do not invent statistics or price changes for missing data."""
    assert price_statistics([])["mean"] is None
    assert price_volatility([])["largest_increase"] is None
    assert price_trend([], 0.005)["direction"] == "insufficient_data"
    assert price_trend(series([1]), 0.005)["direction"] == "insufficient_data"


def test_trend_classification_and_gaps() -> None:
    """Classify changes with explicit absolute tolerance."""
    assert price_trend(series([1, 2]), 0.005)["direction"] == "rising"
    assert price_trend(series([2, 1]), 0.005)["direction"] == "falling"
    assert price_trend(series([1, 1.003]), 0.005)["direction"] == "stable"
    separated = [series([1])[0], series([2])[0]]
    separated[1] = (
        separated[1][0] + timedelta(hours=1),
        separated[1][1] + timedelta(hours=1),
        separated[1][2],
    )
    assert price_trend(separated, 0)["has_gaps"] is True


def test_negative_price_periods_exclude_zero() -> None:
    """Negative means strictly below zero, not zero itself."""
    periods = threshold_periods(series([-0.1, -0.2, 0, -0.3]), 0, True, 15)
    assert len(periods) == 2
    assert periods[0]["duration_minutes"] == 30


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf"), True])
def test_invalid_trend_tolerance(invalid: float) -> None:
    """Reject invalid tolerances explicitly."""
    with pytest.raises(ValueError):
        price_trend(series([1, 2]), invalid)
