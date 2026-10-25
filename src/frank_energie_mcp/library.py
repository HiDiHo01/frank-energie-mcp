"""Bridge helpers for the `python_frank_energie` library."""

from __future__ import annotations

import math
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, Protocol, cast
from zoneinfo import ZoneInfo

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

    async def get_price_threshold_periods(
        self,
        threshold: float,
        comparison: Literal["below", "above"] = "below",
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Group strictly adjacent electricity intervals matching a price threshold."""
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
        ):
            raise ValueError("threshold must be a finite number.")
        if comparison not in ("below", "above"):
            raise ValueError("comparison must be below or above.")
        if resolution not in ("PT15M", "PT60M"):
            raise ValueError("Unsupported price resolution.")
        requested_day = day or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
        async with self.bridge.session() as client:
            prices = await client.prices(requested_day, resolution=resolution)
        normalized = normalize_market_prices(prices)
        step_seconds = {"PT15M": 900, "PT60M": 3600}[resolution]
        result: dict[str, Any] = {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            "threshold": float(threshold),
            "comparison": comparison,
        }
        for energy in ("electricity", "gas"):
            intervals = normalized[energy]
            coverage = _average_series(intervals, requested_day)
            groups: list[dict[str, Any]] = []
            current: list[dict[str, Any]] = []

            for entry in sorted(intervals, key=lambda item: item["date_from"]):
                start = datetime.fromisoformat(entry["date_from"]).astimezone(UTC)
                end = datetime.fromisoformat(entry["date_till"]).astimezone(UTC)
                matches = (
                    entry["total"] < threshold
                    if comparison == "below"
                    else entry["total"] > threshold
                )
                if not matches or (end - start).total_seconds() != step_seconds:
                    if current:
                        groups.append(_threshold_period(current))
                        current = []
                    continue
                if (
                    current
                    and datetime.fromisoformat(current[-1]["date_till"]).astimezone(UTC) != start
                ):
                    groups.append(_threshold_period(current))
                    current = []
                current.append(entry)
            if current:
                groups.append(_threshold_period(current))
            result[energy] = {
                "periods": groups,
                "matching_interval_count": sum(group["interval_count"] for group in groups),
                "interval_count": coverage["interval_count"],
                "coverage_seconds": coverage["coverage_seconds"],
                "expected_seconds": coverage["expected_seconds"],
                "status": coverage["status"],
            }
        return result

    async def get_negative_price_periods(
        self,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Return strictly negative price periods using the shared threshold analyzer."""
        return await self.get_price_threshold_periods(
            threshold=0.0, comparison="below", day=day, resolution=resolution
        )

    async def get_lowest_period(
        self,
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Find the cheapest uninterrupted period by average total price."""
        return await self._get_extreme_period(period_minutes, day, resolution, highest=False)

    async def get_best_start_time(
        self,
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        consumption_kwh: float | None = None,
    ) -> dict[str, Any]:
        """Find the cheapest electricity start time for a fixed-duration load."""
        if consumption_kwh is not None and (
            isinstance(consumption_kwh, bool)
            or not isinstance(consumption_kwh, (int, float))
            or not math.isfinite(consumption_kwh)
            or consumption_kwh < 0
        ):
            raise ValueError("consumption_kwh must be a finite non-negative number.")
        result = await self.get_lowest_period(period_minutes, day, resolution)
        electricity = result["electricity"]
        period = electricity["period"]
        return {
            "date": result["date"],
            "resolution": result["resolution"],
            "period_minutes": result["period_minutes"],
            "start": period["start"] if period is not None else None,
            "end": period["end"] if period is not None else None,
            "average_total": period["average_total"] if period is not None else None,
            "unit": period["unit"] if period is not None else None,
            "consumption_kwh": consumption_kwh,
            "estimated_cost": (
                period["average_total"] * consumption_kwh
                if period is not None and consumption_kwh is not None
                else None
            ),
            "available_interval_count": electricity["available_interval_count"],
            "coverage_seconds": electricity["coverage_seconds"],
            "expected_seconds": electricity["expected_seconds"],
            "status": electricity["status"],
        }

    async def calculate_energy_cost(
        self,
        start: datetime,
        end: datetime,
        consumption_kwh: float,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Estimate electricity cost for uniform consumption over a covered interval."""
        if (
            not isinstance(start, datetime)
            or not isinstance(end, datetime)
            or start.tzinfo is None
            or end.tzinfo is None
            or start.utcoffset() is None
            or end.utcoffset() is None
        ):
            raise ValueError("start and end must be timezone-aware datetimes.")
        start_utc = start.astimezone(UTC)
        end_utc = end.astimezone(UTC)
        if end_utc <= start_utc:
            raise ValueError("end must be later than start.")
        if (
            isinstance(consumption_kwh, bool)
            or not isinstance(consumption_kwh, (int, float))
            or not math.isfinite(consumption_kwh)
            or consumption_kwh < 0
        ):
            raise ValueError("consumption_kwh must be a finite non-negative number.")
        if resolution not in ("PT15M", "PT60M"):
            raise ValueError("Unsupported price resolution.")

        local_tz = ZoneInfo("Europe/Amsterdam")
        first_day = start_utc.astimezone(local_tz).date()
        last_day = (end_utc - timedelta(microseconds=1)).astimezone(local_tz).date()
        if last_day > first_day + timedelta(days=1):
            raise ValueError("The requested period must span at most two Amsterdam dates.")

        intervals: list[dict[str, Any]] = []
        async with self.bridge.session() as client:
            day = first_day
            while day <= last_day:
                prices = await client.prices(day, resolution=resolution)
                intervals.extend(normalize_market_prices(prices)["electricity"])
                day += timedelta(days=1)

        # Each price must cover its complete resolution interval. Clipping is
        # permitted only at the requested start/end boundaries.
        step_seconds = {"PT15M": 900, "PT60M": 3600}[resolution]
        ordered = sorted(intervals, key=lambda entry: entry["date_from"])
        cursor = start_utc
        weighted_total = 0.0
        for entry in ordered:
            price_start = datetime.fromisoformat(entry["date_from"]).astimezone(UTC)
            price_end = datetime.fromisoformat(entry["date_till"]).astimezone(UTC)
            if price_end <= start_utc or price_start >= end_utc:
                continue
            if (price_end - price_start).total_seconds() != step_seconds:
                raise ValueError("Invalid price interval duration.")
            clipped_start = max(price_start, start_utc)
            clipped_end = min(price_end, end_utc)
            if clipped_start != cursor:
                raise ValueError("Electricity price coverage has gaps or overlaps.")
            seconds = (clipped_end - clipped_start).total_seconds()
            weighted_total += seconds * entry["total"]
            cursor = clipped_end
        if cursor != end_utc:
            raise ValueError("Electricity prices do not cover the requested period.")

        duration_seconds = (end_utc - start_utc).total_seconds()
        average_total = weighted_total / duration_seconds
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "resolution": resolution,
            "consumption_kwh": float(consumption_kwh),
            "average_total": average_total,
            "estimated_cost": average_total * consumption_kwh,
            "unit": "kWh",
            "duration_seconds": duration_seconds,
        }

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
            "gas": _extreme_period(normalized["gas"], requested_day, period_minutes, step, highest),
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


def _threshold_period(intervals: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize one validated, uninterrupted group of matching price intervals."""
    start = datetime.fromisoformat(intervals[0]["date_from"]).astimezone(UTC)
    end = datetime.fromisoformat(intervals[-1]["date_till"]).astimezone(UTC)
    return {
        "start": intervals[0]["date_from"],
        "end": intervals[-1]["date_till"],
        "duration_minutes": int((end - start).total_seconds() // 60),
        "interval_count": len(intervals),
        "average_total": sum(item["total"] for item in intervals) / len(intervals),
        "unit": intervals[0]["unit"],
    }


def _average_series(intervals: list[dict[str, Any]], day: date) -> dict[str, Any]:
    """Summarize observed intervals without imputing missing prices."""
    local_zone = ZoneInfo("Europe/Amsterdam")
    start = datetime(day.year, day.month, day.day, tzinfo=local_zone).astimezone(UTC)
    next_day = day + timedelta(days=1)
    end = datetime(next_day.year, next_day.month, next_day.day, tzinfo=local_zone).astimezone(UTC)
    ordered = sorted(intervals, key=lambda interval: datetime.fromisoformat(interval["date_from"]))
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
            else "complete"
            if observed_seconds == day_seconds
            else "incomplete"
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
        starts = [datetime.fromisoformat(entry["date_from"]).astimezone(UTC) for entry in window]
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
