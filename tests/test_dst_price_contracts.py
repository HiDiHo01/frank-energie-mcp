"""Regression coverage for full Amsterdam calendar days across DST transitions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from frank_energie_mcp.price_schemas import normalize_market_prices

AMSTERDAM = ZoneInfo("Europe/Amsterdam")


@pytest.mark.parametrize(
    ("day", "hours"),
    [
        (date(2026, 3, 29), 23),  # Spring: clocks skip 02:00 local.
        (date(2026, 6, 15), 24),  # Ordinary calendar day.
        (date(2026, 10, 25), 25),  # Autumn: 02:00 local occurs twice.
    ],
)
@pytest.mark.parametrize(("resolution_minutes", "resolution"), [(15, "PT15M"), (60, "PT60M")])
def test_full_local_day_price_series_survives_normalization(
    day: date, hours: int, resolution_minutes: int, resolution: str
) -> None:
    """Retain every real interval across DST without dropping repeated local times."""
    start = datetime(day.year, day.month, day.day, tzinfo=AMSTERDAM).astimezone(UTC)
    following = day + timedelta(days=1)
    end = datetime(following.year, following.month, following.day, tzinfo=AMSTERDAM).astimezone(UTC)
    expected_count = hours * 60 // resolution_minutes
    assert end - start == timedelta(hours=hours), resolution

    intervals = [
        SimpleNamespace(
            date_from=start + timedelta(minutes=i * resolution_minutes),
            date_till=start + timedelta(minutes=(i + 1) * resolution_minutes),
            total=0.25,
            per_unit="kWh",
            energy_type="electricity",
        )
        for i in range(expected_count)
    ]
    upstream = SimpleNamespace(
        electricity=SimpleNamespace(price_data=intervals),
        gas=SimpleNamespace(price_data=[]),
    )

    response = normalize_market_prices(upstream)
    electricity = response["electricity"]
    assert len(electricity) == expected_count
    assert response["gas"] == []
    assert datetime.fromisoformat(electricity[0]["date_from"]) == start
    assert datetime.fromisoformat(electricity[-1]["date_till"]) == end
    assert all(
        datetime.fromisoformat(current["date_till"])
        == datetime.fromisoformat(next_interval["date_from"])
        for current, next_interval in zip(electricity, electricity[1:], strict=False)
    )
    assert len({item["date_from"] for item in electricity}) == expected_count
