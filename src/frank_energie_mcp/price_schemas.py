"""Strict, privacy-safe MCP market price response contracts."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PriceInterval(BaseModel):
    """Explicit public fields of one upstream market-price interval."""

    model_config = ConfigDict(extra="forbid", strict=True)

    date_from: datetime
    date_till: datetime
    total: float
    unit: str | None = None
    energy_type: str | None = None


class MarketPriceResponse(BaseModel):
    """Public price intervals; no raw upstream models or customer data."""

    model_config = ConfigDict(extra="forbid", strict=True)

    electricity: list[PriceInterval] = Field(default_factory=list)
    gas: list[PriceInterval] = Field(default_factory=list)


def normalize_interval(price: Any) -> dict[str, Any]:
    """Whitelist and validate the upstream interval without serializing secrets."""
    start = price.date_from
    end = price.date_till
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError("Invalid market-price timestamps.")
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("Market-price intervals must be ordered and timezone-aware.")
    total = price.total
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not isfinite(total):
        raise ValueError("Invalid market-price amount.")
    unit = getattr(price, "per_unit", None) or getattr(price, "unit", None)
    record = PriceInterval(
        date_from=start,
        date_till=end,
        total=float(total),
        unit=unit,
        energy_type=getattr(price, "energy_type", None),
    )
    return record.model_dump(mode="json")


def normalize_market_prices(prices: Any) -> dict[str, Any]:
    """Return bounded, JSON-serializable market prices from upstream PriceData."""
    result: dict[str, list[dict[str, Any]]] = {}
    for energy in ("electricity", "gas"):
        series = getattr(prices, energy)
        entries = getattr(series, "price_data")
        if not isinstance(entries, list) or len(entries) > 200:
            raise ValueError("Invalid market-price series.")
        result[energy] = [normalize_interval(entry) for entry in entries]
    return MarketPriceResponse.model_validate(result).model_dump(mode="json")
