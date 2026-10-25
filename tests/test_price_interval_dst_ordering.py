"""Regression tests for timezone-aware price interval chronology."""

from datetime import UTC, datetime, timedelta, timezone
from math import inf, nan
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from frank_energie_mcp.price_schemas import normalize_interval


@pytest.mark.parametrize(
    "start_fold,end_fold,start_minute,end_minute,valid",
    [
        (0, 1, 45, 15, True),
        (1, 0, 15, 45, False),
        (0, 0, 45, 15, False),
    ],
)
def test_price_interval_uses_utc_order_during_fall_dst_fold(
    start_fold: int, end_fold: int, start_minute: int, end_minute: int, valid: bool
) -> None:
    """Compare absolute instants rather than ambiguous local wall-clock times."""
    zone = ZoneInfo("Europe/Amsterdam")
    start = datetime(2026, 10, 25, 2, start_minute, tzinfo=zone, fold=start_fold)
    end = datetime(2026, 10, 25, 2, end_minute, tzinfo=zone, fold=end_fold)
    price = SimpleNamespace(date_from=start, date_till=end, total=0.2)

    if valid:
        result = normalize_interval(price)
        assert result["date_from"] == start.isoformat()
        assert result["date_till"] == end.isoformat()
    else:
        with pytest.raises(ValueError, match="ordered"):
            normalize_interval(price)


def test_price_interval_accepts_spring_forward_transition() -> None:
    """A real 30-minute interval may jump over the missing local hour."""
    zone = ZoneInfo("Europe/Amsterdam")
    start = datetime(2026, 3, 29, 1, 45, tzinfo=zone)
    end = datetime(2026, 3, 29, 3, 15, tzinfo=zone)
    result = normalize_interval(SimpleNamespace(date_from=start, date_till=end, total=0.2))
    assert result["date_from"] == start.isoformat()
    assert result["date_till"] == end.isoformat()


def test_price_interval_rejects_reverse_order_across_different_offsets() -> None:
    """Different timezone offsets must not mask reversed absolute instants."""
    start = datetime(2026, 3, 29, 3, 15, tzinfo=timezone(timedelta(hours=2)))
    end = datetime(2026, 3, 29, 0, 45, tzinfo=UTC)
    with pytest.raises(ValueError, match="ordered"):
        normalize_interval(SimpleNamespace(date_from=start, date_till=end, total=0.2))


def test_price_interval_rejects_equal_instants_with_different_offsets() -> None:
    """Distinct wall-clock values may represent the same UTC instant."""
    start = datetime(2026, 10, 25, 2, 30, tzinfo=timezone(timedelta(hours=2)))
    end = datetime(2026, 10, 25, 1, 30, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match="ordered"):
        normalize_interval(SimpleNamespace(date_from=start, date_till=end, total=0.2))


@pytest.mark.parametrize("amount", [nan, inf, -inf, True, False, "0.2"])
def test_price_interval_rejects_nonfinite_or_nonnumeric_amount(amount: object) -> None:
    """Do not publish invalid, non-finite, or boolean prices."""
    start = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    end = datetime(2026, 10, 25, 12, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="amount"):
        normalize_interval(SimpleNamespace(date_from=start, date_till=end, total=amount))


@pytest.mark.parametrize("amount", [0, -0.1, 0.2])
def test_price_interval_accepts_finite_prices_including_negative(amount: float) -> None:
    """Negative electricity prices and zero remain valid measurements."""
    start = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    end = datetime(2026, 10, 25, 12, 15, tzinfo=UTC)
    result = normalize_interval(SimpleNamespace(date_from=start, date_till=end, total=amount))
    assert result["total"] == float(amount)
