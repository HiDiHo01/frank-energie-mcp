"""Bridge helpers for the `python_frank_energie` library."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, Protocol, cast
from zoneinfo import ZoneInfo

from .optimization import (
    battery_savings,
    best_start,
    energy_cost,
    split_periods,
    threshold_periods,
    validated_series,
)
from .price_schemas import normalize_interval, normalize_market_prices

PriceResolution = Literal["PT15M", "PT60M"]


class _AsyncFrankEnergie(Protocol):
    """Protocol for the subset of the Frank Energie API used by the MCP layer."""

    async def login(self, username: str, password: str) -> Any:
        """Authenticate with Frank Energie."""

    async def user(self, site_reference: str | None = None) -> Any:
        """Return the current user data."""

    async def UserSites(self) -> Any:  # noqa: N802 - upstream API method name
        """Return authenticated delivery sites."""

    async def invoices(self) -> Any:
        """Return invoice data."""

    async def month_summary(self) -> Any:
        """Return the month summary."""

    async def prices(
        self, start_date: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> Any:
        """Return public market prices for the requested calendar date."""

    async def user_prices(
        self,
        site_reference: str,
        user_country: str,
        start_date: date,
        end_date: date | None = None,
        resolution: str | None = "PT15M",
    ) -> Any:
        """Return customer market prices using the upstream method signature."""

    async def close(self) -> None:
        """Close the underlying HTTP session."""


@dataclass(slots=True, frozen=True)
class FrankEnergieLibraryBridge:
    """Encapsulate access to `python_frank_energie`.

    The bridge keeps the MCP layer isolated from the concrete library import so
    the rest of the repository can be tested against a narrow interface.
    """

    factory: Callable[[], _AsyncFrankEnergie]
    username: str | None = None
    password: str | None = None
    site_reference: str | None = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[_AsyncFrankEnergie]:
        """Create a managed Frank Energie client session."""
        client = self.factory()
        try:
            if self.username is not None and self.password is not None:
                await client.login(self.username, self.password)
            yield client
        finally:
            await client.close()


@dataclass(slots=True, frozen=True)
class FrankEnergieService:
    """High-level service helpers for MCP tool handlers."""

    bridge: FrankEnergieLibraryBridge

    async def get_current_prices(self, resolution: PriceResolution = "PT15M") -> dict[str, Any]:
        """Return the currently applicable upstream electricity and gas records."""
        async with self.bridge.session() as client:
            prices = await client.prices(
                datetime.now(ZoneInfo("Europe/Amsterdam")).date(), resolution=resolution
            )
        return {
            "electricity": _current_price(prices.electricity),
            "gas": _current_price(prices.gas),
        }

    async def get_today_prices(self, resolution: PriceResolution = "PT15M") -> Any:
        """Return today's prices."""
        async with self.bridge.session() as client:
            prices = await client.prices(
                datetime.now(ZoneInfo("Europe/Amsterdam")).date(), resolution=resolution
            )
        return normalize_market_prices(prices)

    async def get_average_prices(
        self, day: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> dict[str, Any]:
        """Average available normalized total prices for an Amsterdam calendar day."""
        requested_day = day or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
        async with self.bridge.session() as client:
            prices = await client.prices(requested_day, resolution=resolution)
        normalized = normalize_market_prices(prices)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            "electricity": _average_series(normalized["electricity"], requested_day),
            "gas": _average_series(normalized["gas"], requested_day),
        }

    async def get_lowest_price(
        self, day: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> dict[str, Any]:
        """Return the lowest available total-price interval for each energy type."""
        return await self._get_extreme_prices(day, resolution, highest=False)

    async def get_highest_price(
        self, day: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> dict[str, Any]:
        """Return the highest available total-price interval for each energy type."""
        return await self._get_extreme_prices(day, resolution, highest=True)

    async def _get_extreme_prices(
        self, day: date | None, resolution: PriceResolution, *, highest: bool
    ) -> dict[str, Any]:
        """Select extreme intervals from normalized public price records."""
        requested_day = day or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
        async with self.bridge.session() as client:
            prices = await client.prices(requested_day, resolution=resolution)
        normalized = normalize_market_prices(prices)
        result: dict[str, Any] = {
            "date": requested_day.isoformat(),
            "resolution": resolution,
        }
        for energy in ("electricity", "gas"):
            intervals = normalized[energy]
            coverage = _average_series(intervals, requested_day)
            selected = (
                (max if highest else min)(intervals, key=lambda entry: entry["total"])
                if intervals
                else None
            )
            result[energy] = {
                "price": selected,
                "interval_count": coverage["interval_count"],
                "coverage_seconds": coverage["coverage_seconds"],
                "expected_seconds": coverage["expected_seconds"],
                "status": coverage["status"],
            }
        return result

    async def get_lowest_period(
        self,
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Find the cheapest uninterrupted period by average total price."""
        return await self._get_extreme_period(period_minutes, day, resolution, highest=False)

    async def get_highest_period(
        self,
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Find the most expensive uninterrupted period by average total price."""
        return await self._get_extreme_period(period_minutes, day, resolution, highest=True)

    async def _get_extreme_period(
        self,
        period_minutes: int,
        day: date | None,
        resolution: PriceResolution,
        *,
        highest: bool,
    ) -> dict[str, Any]:
        """Fetch once and find a contiguous fixed-duration window per energy type."""
        step = {"PT15M": 15, "PT60M": 60}[resolution]
        if isinstance(period_minutes, bool) or not isinstance(period_minutes, int):
            raise ValueError("period_minutes must be a positive integer.")
        if period_minutes <= 0 or period_minutes % step:
            raise ValueError("period_minutes must be a positive multiple of the resolution.")
        requested_day = day or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
        async with self.bridge.session() as client:
            prices = await client.prices(requested_day, resolution=resolution)
        normalized = normalize_market_prices(prices)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            "period_minutes": period_minutes,
            "electricity": _extreme_period(
                normalized["electricity"], requested_day, period_minutes, step, highest
            ),
            "gas": _extreme_period(
                normalized["gas"], requested_day, period_minutes, step, highest
            ),
        }

    async def _optimization_data(
        self, day: date | None, resolution: PriceResolution
    ) -> tuple[date, dict[str, Any]]:
        """Retrieve one bounded normalized market-price response."""
        requested_day = day or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
        async with self.bridge.session() as client:
            prices = await client.prices(requested_day, resolution=resolution)
        return requested_day, normalize_market_prices(prices)

    async def get_best_start_time(
        self,
        duration_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        earliest_start: datetime | None = None,
        latest_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Return the cheapest continuous start window for each energy type."""
        for bound in (earliest_start, latest_end):
            if bound is not None and (bound.tzinfo is None or bound.utcoffset() is None):
                raise ValueError("Time bounds must be timezone-aware.")
        earliest = earliest_start.astimezone(UTC) if earliest_start else None
        latest = latest_end.astimezone(UTC) if latest_end else None
        if earliest and latest and earliest >= latest:
            raise ValueError("earliest_start must precede latest_end.")
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            "duration_minutes": duration_minutes,
            **{
                energy: best_start(
                    validated_series(prices[energy], requested_day, resolution),
                    duration_minutes,
                    resolution,
                    earliest,
                    latest,
                )
                for energy in ("electricity", "gas")
            },
        }

    async def calculate_energy_cost(
        self,
        power_kw: float,
        duration_minutes: int,
        start_time: datetime,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Estimate fixed-power electricity consumption from normalized total prices."""
        if start_time.tzinfo is None or start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware.")
        start = start_time.astimezone(UTC)
        requested_day = start.astimezone(ZoneInfo("Europe/Amsterdam")).date()
        _, prices = await self._optimization_data(requested_day, resolution)
        result = energy_cost(
            validated_series(prices["electricity"], requested_day, resolution),
            start,
            duration_minutes,
            power_kw,
            resolution,
        )
        return {"date": requested_day.isoformat(), "resolution": resolution, **result}

    async def get_price_threshold_periods(
        self,
        threshold: float,
        below: bool = True,
        minimum_duration_minutes: int = 15,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Group consecutive intervals strictly below or above a total-price threshold."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            **{
                energy: threshold_periods(
                    validated_series(prices[energy], requested_day, resolution),
                    threshold,
                    below,
                    minimum_duration_minutes,
                )
                for energy in ("electricity", "gas")
            },
        }

    async def get_best_split_periods(
        self,
        total_minutes: int,
        minimum_block_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Choose the cheapest nonoverlapping full-length blocks per energy type."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            **{
                energy: split_periods(
                    validated_series(prices[energy], requested_day, resolution),
                    total_minutes,
                    minimum_block_minutes,
                    resolution,
                )
                for energy in ("electricity", "gas")
            },
        }

    async def calculate_battery_savings(
        self,
        capacity_kwh: float,
        charge_power_kw: float,
        discharge_power_kw: float,
        round_trip_efficiency: float,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Estimate a single idealized battery arbitrage cycle using public prices."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            "electricity": battery_savings(
                validated_series(prices["electricity"], requested_day, resolution),
                capacity_kwh,
                charge_power_kw,
                discharge_power_kw,
                round_trip_efficiency,
                resolution,
            ),
        }

    async def get_tomorrow_prices(self, resolution: PriceResolution = "PT15M") -> Any:
        """Return tomorrow's prices."""
        tomorrow = datetime.now(ZoneInfo("Europe/Amsterdam")).date() + timedelta(days=1)
        async with self.bridge.session() as client:
            prices = await client.prices(tomorrow, resolution=resolution)
        return normalize_market_prices(prices)

    async def get_gas_price(self, resolution: PriceResolution = "PT15M") -> dict[str, Any] | None:
        """Return the currently applicable gas price, or None if unavailable."""
        async with self.bridge.session() as client:
            prices = await client.prices(
                datetime.now(ZoneInfo("Europe/Amsterdam")).date(), resolution=resolution
            )
        return _current_price(prices.gas)

    async def get_account(self) -> Any:
        """Return account data for the configured delivery site."""
        if not self.bridge.site_reference:
            raise RuntimeError("Account access requires FRANK_ENERGIE_SITE_REFERENCE.")
        if not self.bridge.username or not self.bridge.password:
            raise RuntimeError("Account access requires Frank Energie credentials.")
        async with self.bridge.session() as client:
            return await client.user(self.bridge.site_reference)

    async def list_sites(self) -> Any:
        """Return the available sites."""
        if not self.bridge.username or not self.bridge.password:
            raise RuntimeError("Site access requires Frank Energie credentials.")
        async with self.bridge.session() as client:
            return await client.UserSites()


def _average_series(intervals: list[dict[str, Any]], day: date) -> dict[str, Any]:
    """Summarize observed intervals without imputing missing prices."""
    local_zone = ZoneInfo("Europe/Amsterdam")
    start = datetime(day.year, day.month, day.day, tzinfo=local_zone).astimezone(UTC)
    next_day = day + timedelta(days=1)
    end = datetime(next_day.year, next_day.month, next_day.day, tzinfo=local_zone).astimezone(UTC)
    ordered = sorted(
        intervals, key=lambda interval: datetime.fromisoformat(interval["date_from"])
    )
    observed_seconds = 0.0
    previous_end: datetime | None = None
    for interval in ordered:
        interval_start = datetime.fromisoformat(interval["date_from"]).astimezone(UTC)
        interval_end = datetime.fromisoformat(interval["date_till"]).astimezone(UTC)
        if interval_start < start or interval_end > end:
            raise ValueError("Price interval is outside the requested calendar day.")
        if previous_end is not None and interval_start < previous_end:
            raise ValueError("Overlapping or duplicate price intervals.")
        observed_seconds += (interval_end - interval_start).total_seconds()
        previous_end = interval_end

    day_seconds = (end - start).total_seconds()
    return {
        "average_total": (
            sum(float(interval["total"]) for interval in ordered) / len(ordered)
            if ordered
            else None
        ),
        "interval_count": len(ordered),
        "first_interval": ordered[0]["date_from"] if ordered else None,
        "last_interval": ordered[-1]["date_till"] if ordered else None,
        "coverage_seconds": int(observed_seconds),
        "expected_seconds": int(day_seconds),
        "complete": bool(ordered) and observed_seconds == day_seconds,
        "status": (
            "empty"
            if not ordered
            else "complete" if observed_seconds == day_seconds else "incomplete"
        ),
    }


def _extreme_period(
    intervals: list[dict[str, Any]],
    day: date,
    period_minutes: int,
    step_minutes: int,
    highest: bool,
) -> dict[str, Any]:
    """Find a fixed-size uninterrupted window; ignore gaps and partial windows."""
    coverage = _average_series(intervals, day)
    ordered = sorted(intervals, key=lambda entry: entry["date_from"])
    window_size = period_minutes // step_minutes
    best: dict[str, Any] | None = None
    step_seconds = step_minutes * 60
    for index in range(len(ordered) - window_size + 1):
        window = ordered[index : index + window_size]
        starts = [
            datetime.fromisoformat(entry["date_from"]).astimezone(UTC) for entry in window
        ]
        ends = [datetime.fromisoformat(entry["date_till"]).astimezone(UTC) for entry in window]
        if any(
            (end - start).total_seconds() != step_seconds
            for start, end in zip(starts, ends, strict=True)
        ):
            continue
        if any(ends[offset] != starts[offset + 1] for offset in range(window_size - 1)):
            continue
        average = sum(entry["total"] for entry in window) / window_size
        if best is None or (
            average > best["average_total"] if highest else average < best["average_total"]
        ):
            best = {
                "start": window[0]["date_from"],
                "end": window[-1]["date_till"],
                "average_total": average,
                "interval_count": window_size,
                "unit": window[0]["unit"],
            }
    return {
        "period": best,
        "available_interval_count": coverage["interval_count"],
        "coverage_seconds": coverage["coverage_seconds"],
        "expected_seconds": coverage["expected_seconds"],
        "status": coverage["status"],
    }


def _current_price(series: Any) -> dict[str, Any] | None:
    """Return the active upstream interval as a JSON-compatible record."""
    price = series.current_hour
    if price is None:
        return None
    return normalize_interval(price)


def default_library_bridge() -> FrankEnergieLibraryBridge:
    """Return the default bridge for `python_frank_energie`.

    Importing the library happens lazily so the MCP package remains importable
    even if the dependency is missing during early scaffolding.
    """

    def _factory() -> _AsyncFrankEnergie:
        from python_frank_energie.frank_energie import FrankEnergie  # type: ignore[import-untyped]

        return cast(_AsyncFrankEnergie, FrankEnergie())

    username = os.environ.get("FRANK_ENERGIE_USERNAME") or None
    password = os.environ.get("FRANK_ENERGIE_PASSWORD") or None
    if (username is None) != (password is None):
        raise ValueError("Both FRANK_ENERGIE_USERNAME and FRANK_ENERGIE_PASSWORD are required.")
    return FrankEnergieLibraryBridge(
        factory=_factory,
        username=username,
        password=password,
        site_reference=os.environ.get("FRANK_ENERGIE_SITE_REFERENCE") or None,
    )


def default_service() -> FrankEnergieService:
    """Return the default high-level service helper."""
    return FrankEnergieService(bridge=default_library_bridge())
