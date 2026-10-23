"""Regression tests for the public, privacy-safe MCP response contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from json import dumps
from math import inf, nan
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from frank_energie_mcp.price_schemas import (
    MarketPriceResponse,
    PriceInterval,
    normalize_interval,
    normalize_market_prices,
)
from frank_energie_mcp.server import AccountResponse, SitesResponse, _count_sites


def _interval(**overrides: Any) -> SimpleNamespace:
    """Build a synthetic upstream interval with a private field."""
    start = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
    fields: dict[str, Any] = {
        "date_from": start,
        "date_till": start + timedelta(minutes=15),
        "total": 0.25,
        "per_unit": "kWh",
        "energy_type": "electricity",
        "authToken": "private-token",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _prices(electricity: list[Any], gas: list[Any] | None = None) -> SimpleNamespace:
    """Build synthetic upstream series without network access."""
    return SimpleNamespace(
        electricity=SimpleNamespace(price_data=electricity),
        gas=SimpleNamespace(price_data=[] if gas is None else gas),
    )


def test_interval_contract_has_only_public_json_fields() -> None:
    """Exclude upstream secrets and preserve valid ISO timestamps."""
    result = normalize_interval(_interval(unit="ignored"))
    assert set(result) == {"date_from", "date_till", "total", "unit", "energy_type"}
    assert result["unit"] == "kWh"
    assert result["total"] == 0.25
    assert datetime.fromisoformat(result["date_from"]).tzinfo is not None
    assert "private-token" not in dumps(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"date_from": "2026-10-23T10:00:00Z"},
        {"date_till": "2026-10-23T10:15:00Z"},
        {"date_from": datetime(2026, 10, 23, 10, 0)},
        {"date_till": datetime(2026, 10, 23, 10, 15)},
        {"date_till": datetime(2026, 10, 23, 10, 0, tzinfo=UTC)},
        {"date_till": datetime(2026, 10, 23, 9, 59, tzinfo=UTC)},
    ],
)
def test_interval_rejects_invalid_timestamps(changes: dict[str, Any]) -> None:
    """Reject strings, naive datetimes, and unordered intervals."""
    with pytest.raises(ValueError):
        normalize_interval(_interval(**changes))


@pytest.mark.parametrize("amount", [nan, inf, -inf, True, False, None, "0.25"])
def test_interval_rejects_invalid_amounts(amount: Any) -> None:
    """Never expose non-finite or incorrectly typed prices."""
    with pytest.raises(ValueError):
        normalize_interval(_interval(total=amount))


def test_interval_accepts_finite_integer_amount() -> None:
    """An upstream integer price is normalized to a JSON float."""
    assert normalize_interval(_interval(total=1))["total"] == 1.0


def test_interval_uses_optional_unit_fallback() -> None:
    """Use the upstream unit when per_unit is absent."""
    assert normalize_interval(_interval(per_unit=None, unit="m3"))["unit"] == "m3"


def test_market_prices_normalize_both_series() -> None:
    """Both series use the same public schema without leaking extra fields."""
    electricity = _interval()
    gas = _interval(per_unit="m3", energy_type="gas")
    result = normalize_market_prices(_prices([electricity], [gas]))
    assert set(result) == {"electricity", "gas"}
    assert result["gas"][0]["unit"] == "m3"
    assert result["gas"][0]["energy_type"] == "gas"
    assert "private-token" not in dumps(result)
    assert datetime.fromisoformat(result["electricity"][0]["date_till"]).tzinfo is not None


@pytest.mark.parametrize("count", [0, 1, 200])
def test_market_series_accepts_bounded_lengths(count: int) -> None:
    """The documented per-energy limit is inclusive."""
    result = normalize_market_prices(_prices([_interval()] * count))
    assert len(result["electricity"]) == count


@pytest.mark.parametrize("entries", [[None] * 201, None, "not-a-list", {}])
def test_market_series_rejects_unsupported_shapes(entries: Any) -> None:
    """Reject unbounded and non-list upstream data."""
    with pytest.raises(ValueError, match="Invalid market-price series"):
        normalize_market_prices(_prices(entries))


def test_strict_response_models_reject_unknown_fields() -> None:
    """No accidental account or interval fields enter the public schemas."""
    with pytest.raises(ValidationError):
        PriceInterval(
            date_from=datetime(2026, 10, 23, 10, tzinfo=UTC),
            date_till=datetime(2026, 10, 23, 11, tzinfo=UTC),
            total=0.25,
            token="private",
        )
    with pytest.raises(ValidationError):
        MarketPriceResponse.model_validate({"electricity": [], "gas": [], "token": "private"})
    with pytest.raises(ValidationError):
        AccountResponse.model_validate({"authenticated": True, "email": "private"})
    with pytest.raises(ValidationError):
        SitesResponse.model_validate({"count": 1, "address": "private"})


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([], 0),
        ([{}, {}], 2),
        ({"sites": [1]}, 1),
        ({"deliverySites": [1, 2]}, 2),
        (SimpleNamespace(deliverySites=[1, 2, 3]), 3),
    ],
)
def test_site_count_contract(payload: Any, expected: int) -> None:
    """Return only a site count for recognized upstream collection shapes."""
    assert _count_sites(payload) == expected


@pytest.mark.parametrize("payload", [{}, {"sites": "private"}, object()])
def test_site_count_rejects_unknown_shapes(payload: Any) -> None:
    """Unknown site structures fail closed."""
    with pytest.raises(ValueError, match="Unexpected site response structure"):
        _count_sites(payload)
