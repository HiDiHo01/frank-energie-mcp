"""Regression tests for timezone-aware price interval chronology."""

from datetime import datetime
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
