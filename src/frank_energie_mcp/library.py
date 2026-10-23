"""Bridge helpers for the `python_frank_energie` library."""

from __future__ import annotations

import os
from math import isfinite
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
    price_statistics,
    price_volatility,
    price_trend,
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

    async def user_country(self) -> Any:
        """Return the upstream authenticated user's country payload."""

    async def enode_chargers(self, site_reference: str, start_date: date) -> Any:
        """Return upstream charging devices for a site and date."""

    async def period_usage_and_costs(
        self, site_reference: str, start_date: str
    ) -> Any:
        """Return upstream period usage and cost categories."""

    async def meter_readings(self, site_reference: str) -> Any:
        """Return upstream daily consumption records for a delivery site."""

    async def invoices(self, site_reference: str) -> Any:
        """Return invoice data."""

    async def month_insights(self, site_reference: str, date: str) -> Any:
        """Return upstream monthly usage and cost insights."""

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

    async def smart_batteries(self) -> Any:
        """Return linked smart batteries."""

    async def smart_pv_systems(self) -> Any:
        """Return linked solar PV systems."""

    async def enode_vehicles(self) -> Any:
        """Return linked electric vehicles."""

    async def smart_hvac_status(self) -> Any:
        """Return authenticated smart HVAC status."""

    async def user_smart_feed_in(self) -> Any:
        """Return the current smart feed-in enrollment state."""

    async def contract_price_resolution_state(self, connection_id: str | None = None) -> Any:
        """Return the current contract price resolution state."""

    async def smart_battery_sessions(
        self, device_id: str, start_date: date, end_date: date
    ) -> Any:
        """Return upstream trading sessions for a linked smart battery."""

    async def smart_battery_details(self, device_id: str) -> Any:
        """Return one linked smart battery detail model."""

    async def smart_pv_system_summary(self, device_id: str) -> Any:
        """Return one linked solar PV system summary."""

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

    async def get_negative_price_periods(
        self,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        minimum_duration_minutes: int = 15,
    ) -> dict[str, Any]:
        """Find consecutive negative-total electricity price intervals."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            "electricity": threshold_periods(
                validated_series(prices["electricity"], requested_day, resolution),
                0.0, True, minimum_duration_minutes,
            ),
        }

    async def get_price_trend(
        self,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        stable_tolerance: float = 0.005,
    ) -> dict[str, Any]:
        """Classify first-to-last total price changes separately by energy type."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            **{
                energy: price_trend(
                    validated_series(prices[energy], requested_day, resolution),
                    stable_tolerance,
                )
                for energy in ("electricity", "gas")
            },
        }

    async def get_price_volatility(
        self,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Compute population spread and adjacent price changes."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            **{
                energy: price_volatility(
                    validated_series(prices[energy], requested_day, resolution)
                )
                for energy in ("electricity", "gas")
            },
        }

    async def get_price_statistics(
        self,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Return mean, median, percentiles, minimum and maximum total prices."""
        requested_day, prices = await self._optimization_data(day, resolution)
        return {
            "date": requested_day.isoformat(),
            "resolution": resolution,
            **{
                energy: price_statistics(
                    validated_series(prices[energy], requested_day, resolution)
                )
                for energy in ("electricity", "gas")
            },
        }

    async def compare_days(
        self,
        first_day: date,
        second_day: date,
        resolution: PriceResolution = "PT15M",
    ) -> dict[str, Any]:
        """Compare available total-price distributions across two local days."""
        first_date, first_prices = await self._optimization_data(first_day, resolution)
        second_date, second_prices = await self._optimization_data(second_day, resolution)
        first = {
            energy: price_statistics(
                validated_series(first_prices[energy], first_date, resolution)
            )
            for energy in ("electricity", "gas")
        }
        second = {
            energy: price_statistics(
                validated_series(second_prices[energy], second_date, resolution)
            )
            for energy in ("electricity", "gas")
        }
        return {
            "resolution": resolution,
            "first": {"date": first_date.isoformat(), **first},
            "second": {"date": second_date.isoformat(), **second},
            "mean_difference": {
                energy: (
                    second[energy]["mean"] - first[energy]["mean"]
                    if first[energy]["mean"] is not None
                    and second[energy]["mean"] is not None else None
                )
                for energy in ("electricity", "gas")
            },
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

    async def _linked_device_count(self, operation: str, field: str) -> dict[str, int]:
        """Return only a collection count, never identifiers or device metadata."""
        if not self.bridge.username or not self.bridge.password:
            raise RuntimeError("Device access requires Frank Energie credentials.")
        async with self.bridge.session() as client:
            data = await getattr(client, operation)()
        if data is None:
            return {"count": 0}
        devices = getattr(data, field, None)
        if not isinstance(devices, list):
            raise ValueError("Unexpected upstream device collection.")
        return {"count": len(devices)}

    async def get_smart_battery_count(self) -> dict[str, int]:
        """Count linked smart batteries without exposing device information."""
        return await self._linked_device_count("smart_batteries", "batteries")

    async def get_smart_pv_system_count(self) -> dict[str, int]:
        """Count linked smart solar systems without exposing device information."""
        return await self._linked_device_count("smart_pv_systems", "systems")

    async def get_electric_vehicle_count(self) -> dict[str, int]:
        """Count linked Enode electric vehicles without exposing identifiers."""
        return await self._linked_device_count("enode_vehicles", "vehicles")

    def _require_credentials(self) -> None:
        """Reject account-scoped requests without configured credentials."""
        if not self.bridge.username or not self.bridge.password:
            raise RuntimeError("Account access requires Frank Energie credentials.")

    async def get_smart_hvac_status(self) -> dict[str, bool | None]:
        """Return non-identifying smart HVAC activation and availability flags."""
        self._require_credentials()
        async with self.bridge.session() as client:
            state = await client.smart_hvac_status()
        if state is None:
            return {
                "available": False,
                "is_activated": None,
                "is_available_in_country": None,
            }
        activated = getattr(state, "isActivated", None)
        in_country = getattr(state, "isAvailableInCountry", None)
        if activated is not None and type(activated) is not bool:
            raise ValueError("Unexpected smart HVAC activation flag.")
        if in_country is not None and type(in_country) is not bool:
            raise ValueError("Unexpected smart HVAC country availability flag.")
        return {
            "available": True,
            "is_activated": activated,
            "is_available_in_country": in_country,
        }

    async def get_smart_feed_in_status(self) -> dict[str, bool | None]:
        """Return allowlisted feed-in eligibility flags, never user identifiers."""
        self._require_credentials()
        async with self.bridge.session() as client:
            state = await client.user_smart_feed_in()
        if state is None:
            return {
                "available": False,
                "is_activated": None,
                "has_accepted_terms": None,
                "is_app_onboarding_available": None,
                "is_available_in_country": None,
            }
        fields = (
            "is_activated",
            "has_accepted_terms",
            "is_app_onboarding_available",
            "is_available_in_country",
        )
        flags = {key: getattr(state, key, None) for key in fields}
        if any(type(value) is not bool for value in flags.values()):
            raise ValueError("Unexpected smart feed-in response structure.")
        return {"available": True, **flags}

    async def get_contract_price_resolution_state(
        self, connection_id: str
    ) -> dict[str, Any]:
        """Read contract resolution options without changing the contract."""
        self._require_credentials()
        if not isinstance(connection_id, str) or not connection_id.strip():
            raise ValueError("connection_id must be a non-empty string.")
        async with self.bridge.session() as client:
            state = await client.contract_price_resolution_state(connection_id)
        if state is None:
            return {"available": False}
        active = getattr(state, "active_option", None)
        options = getattr(state, "available_options", None)
        can_change = getattr(state, "is_change_request_possible", None)
        if (
            active is not None and not isinstance(active, str)
            or not isinstance(options, list)
            or not all(isinstance(option, str) for option in options)
            or type(can_change) is not bool
        ):
            raise ValueError("Unexpected contract resolution response structure.")
        return {
            "available": True,
            "active_option": active,
            "available_options": options,
            "is_change_request_possible": can_change,
        }

    async def get_ev_charger_statistics(self, start_date: date) -> dict[str, int]:
        """Count linked EV chargers and supported features without identifiers."""
        self._require_credentials()
        if not self.bridge.site_reference:
            raise RuntimeError("Charger access requires FRANK_ENERGIE_SITE_REFERENCE.")
        if not isinstance(start_date, date) or isinstance(start_date, datetime):
            raise ValueError("start_date must be a calendar date.")
        async with self.bridge.session() as client:
            data = await client.enode_chargers(self.bridge.site_reference, start_date)
        chargers = getattr(data, "chargers", None)
        if not isinstance(chargers, list):
            raise ValueError("Unexpected EV charger response structure.")
        reachable_count = 0
        smart_capable_count = 0
        smart_enabled_count = 0
        for charger in chargers:
            reachable = getattr(charger, "is_reachable", None)
            capable = getattr(charger, "can_smart_charge", None)
            settings = getattr(charger, "charge_settings", None)
            enabled = getattr(settings, "is_smart_charging_enabled", None)
            if any(type(value) is not bool for value in (reachable, capable, enabled)):
                raise ValueError("Unexpected EV charger capability flags.")
            reachable_count += int(reachable)
            smart_capable_count += int(capable)
            smart_enabled_count += int(enabled)
        return {
            "charger_count": len(chargers),
            "reachable_count": reachable_count,
            "smart_capable_count": smart_capable_count,
            "smart_enabled_count": smart_enabled_count,
        }

    async def get_account_country(self) -> dict[str, str]:
        """Return only the account's ISO country code, without personal data."""
        self._require_credentials()
        async with self.bridge.session() as client:
            account = await client.user_country()
        country = getattr(account, "countryCode", None)
        if (
            not isinstance(country, str)
            or len(country) != 2
            or not country.isascii()
            or not country.isalpha()
            or country != country.upper()
        ):
            raise ValueError("Unexpected account country code.")
        return {"country_code": country}

    async def get_monthly_cost_insights(self, month: str) -> dict[str, Any]:
        """Read upstream expected and actual monthly costs without account metadata."""
        self._require_credentials()
        if not self.bridge.site_reference:
            raise RuntimeError("Monthly insights require FRANK_ENERGIE_SITE_REFERENCE.")
        if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
            raise ValueError("month must be in YYYY-MM format.")
        try:
            parsed_month = date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise ValueError("month must be a valid YYYY-MM calendar month.") from exc
        if parsed_month.strftime("%Y-%m") != month:
            raise ValueError("month must be in YYYY-MM format.")
        async with self.bridge.session() as client:
            insights = await client.month_insights(self.bridge.site_reference, month)
        if insights is None:
            return {"available": False, "month": month}
        fields = (
            "expectedCosts",
            "expectedCostsGas",
            "expectedCostsFixed",
            "expectedCostsElectricity",
            "expectedCostsFeedIn",
            "expectedCostsUntilLastMeterReading",
            "actualCostsUntilLastMeterReading",
        )
        result: dict[str, Any] = {"available": True, "month": month}
        for field in fields:
            value = getattr(insights, field, None)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError("Unexpected monthly cost value.")
            result[field] = float(value) if value is not None else None
        return result

    async def get_period_usage_and_costs(
        self, start_date: date
    ) -> dict[str, Any]:
        """Return non-identifying usage and costs for an upstream billing period."""
        self._require_credentials()
        if not self.bridge.site_reference:
            raise RuntimeError("Period access requires FRANK_ENERGIE_SITE_REFERENCE.")
        if not isinstance(start_date, date) or isinstance(start_date, datetime):
            raise ValueError("start_date must be a calendar date.")
        async with self.bridge.session() as client:
            period = await client.period_usage_and_costs(
                self.bridge.site_reference, start_date.isoformat()
            )
        if period is None:
            return {"available": False, "start_date": start_date.isoformat()}
        categories: dict[str, dict[str, Any] | None] = {}
        for name in ("electricity", "gas", "feed_in"):
            category = getattr(period, name, None)
            if category is None:
                categories[name] = None
                continue
            unit = getattr(category, "unit", None)
            if not isinstance(unit, str) or not unit:
                raise ValueError("Unexpected period energy unit.")
            entry: dict[str, Any] = {"unit": unit}
            for key in ("usage_total", "costs_total"):
                value = getattr(category, key, None)
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                ):
                    raise ValueError("Unexpected period usage or cost total.")
                entry[key] = float(value) if value is not None else None
            categories[name] = entry
        return {
            "available": True,
            "start_date": start_date.isoformat(),
            "categories": categories,
        }

    async def get_daily_consumption_statistics(
        self, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """Aggregate recorded daily kWh without exposing account identifiers."""
        self._require_credentials()
        if not self.bridge.site_reference:
            raise RuntimeError("Consumption access requires FRANK_ENERGIE_SITE_REFERENCE.")
        if (
            not isinstance(start_date, date)
            or isinstance(start_date, datetime)
            or not isinstance(end_date, date)
            or isinstance(end_date, datetime)
            or end_date < start_date
            or (end_date - start_date).days > 366
        ):
            raise ValueError("Provide an ordered date range of at most 366 days.")
        async with self.bridge.session() as client:
            consumption = await client.meter_readings(self.bridge.site_reference)
        if consumption is None:
            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "day_count": 0,
                "total_kwh": 0.0,
                "average_daily_kwh": None,
            }
        records = getattr(consumption, "daily_consumption", None)
        if not isinstance(records, list):
            raise ValueError("Unexpected consumption response structure.")
        selected: dict[date, float] = {}
        for record in records:
            raw_day = getattr(record, "date", None)
            raw_value = getattr(record, "consumption_kwh", None)
            if not isinstance(raw_day, str):
                raise ValueError("Unexpected consumption date.")
            try:
                reading_day = date.fromisoformat(raw_day)
            except ValueError as exc:
                raise ValueError("Unexpected consumption date.") from exc
            if reading_day < start_date or reading_day > end_date:
                continue
            if (
                isinstance(raw_value, bool)
                or not isinstance(raw_value, (int, float))
                or not isfinite(raw_value)
                or raw_value < 0
            ):
                raise ValueError("Unexpected daily consumption amount.")
            if reading_day in selected:
                raise ValueError("Duplicate daily consumption date.")
            selected[reading_day] = float(raw_value)
        total = sum(selected.values())
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "day_count": len(selected),
            "total_kwh": total,
            "average_daily_kwh": total / len(selected) if selected else None,
        }

    async def get_invoice_statistics(self, year: int) -> dict[str, Any]:
        """Aggregate invoice amounts for a year without returning invoice IDs."""
        self._require_credentials()
        if not self.bridge.site_reference:
            raise RuntimeError("Invoice access requires FRANK_ENERGIE_SITE_REFERENCE.")
        if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
            raise ValueError("year must be an integer between 2000 and 2100.")
        async with self.bridge.session() as client:
            invoices = await client.invoices(self.bridge.site_reference)
        records = getattr(invoices, "all_periods_invoices", None)
        if not isinstance(records, list):
            raise ValueError("Unexpected invoice response structure.")
        amounts: list[float] = []
        for invoice in records:
            start = getattr(invoice, "StartDate", None)
            amount = getattr(invoice, "TotalAmount", None)
            if not isinstance(start, datetime) or start.tzinfo is None:
                raise ValueError("Unexpected invoice start date.")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                raise ValueError("Unexpected invoice amount.")
            if not isfinite(amount):
                raise ValueError("Invoice amount must be finite.")
            if start.astimezone(ZoneInfo("Europe/Amsterdam")).year == year:
                amounts.append(float(amount))
        return {
            "year": year,
            "invoice_count": len(amounts),
            "total_amount": sum(amounts),
            "average_amount": sum(amounts) / len(amounts) if amounts else None,
        }

    async def get_smart_pv_system_summary(self, device_id: str) -> dict[str, Any]:
        """Return only status and totals for a PV system, without device IDs."""
        self._require_credentials()
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string.")
        async with self.bridge.session() as client:
            summary = await client.smart_pv_system_summary(device_id)
        if summary is None:
            return {"available": False}
        from enum import Enum

        result: dict[str, Any] = {"available": True}
        for field in ("operational_status", "steering_status"):
            value = getattr(summary, field, None)
            if not isinstance(value, (str, Enum)):
                raise ValueError("Unexpected PV system status.")
            result[field] = str(value.value if isinstance(value, Enum) else value)
        for field in ("total_bonus", "total_result"):
            value = getattr(summary, field, None)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError("Unexpected PV system total.")
            result[field] = float(value) if value is not None else None
        return result

    async def get_smart_battery_session_statistics(
        self, device_id: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """Summarize a battery's trading sessions without revealing device data."""
        self._require_credentials()
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string.")
        if (
            not isinstance(start_date, date)
            or isinstance(start_date, datetime)
            or not isinstance(end_date, date)
            or isinstance(end_date, datetime)
            or end_date < start_date
            or (end_date - start_date).days > 366
        ):
            raise ValueError("Provide an ordered date range of at most 366 days.")
        async with self.bridge.session() as client:
            data = await client.smart_battery_sessions(device_id, start_date, end_date)
        if data is None:
            return {
                "available": False,
                "session_count": 0,
                "total_session_result": None,
                "average_session_result": None,
            }
        sessions = getattr(data, "sessions", None)
        if not isinstance(sessions, list):
            raise ValueError("Unexpected battery sessions response structure.")
        results: list[float] = []
        for session in sessions:
            result = getattr(session, "result", None)
            if result is None:
                continue
            if (
                isinstance(result, bool)
                or not isinstance(result, (int, float))
                or not isfinite(result)
            ):
                raise ValueError("Unexpected battery session result.")
            results.append(float(result))
        total = sum(results)
        return {
            "available": True,
            "session_count": len(sessions),
            "result_count": len(results),
            "total_session_result": total if results else None,
            "average_session_result": total / len(results) if results else None,
        }

    async def get_smart_battery_status(self, device_id: str) -> dict[str, Any]:
        """Read a battery's current state without exposing identifiers or settings."""
        self._require_credentials()
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device_id must be a non-empty string.")
        async with self.bridge.session() as client:
            details = await client.smart_battery_details(device_id)
        if details is None:
            return {"available": False}
        summary = getattr(details, "smart_battery_summary", None)
        battery = getattr(details, "smart_battery", None)
        if summary is None or battery is None:
            raise ValueError("Unexpected smart battery detail response.")
        from enum import Enum

        charge = getattr(summary, "last_known_state_of_charge", None)
        status = getattr(summary, "last_known_status", None)
        updated = getattr(summary, "last_update", None)
        capacity = getattr(battery, "capacity", None)
        if isinstance(charge, bool) or not isinstance(charge, int) or not 0 <= charge <= 100:
            raise ValueError("Unexpected battery state of charge.")
        if not isinstance(status, (str, Enum)):
            raise ValueError("Unexpected battery status.")
        if not isinstance(updated, datetime) or updated.tzinfo is None:
            raise ValueError("Unexpected battery update time.")
        if capacity is not None and (
            isinstance(capacity, bool)
            or not isinstance(capacity, (int, float))
            or not isfinite(capacity)
            or capacity < 0
        ):
            raise ValueError("Unexpected battery capacity.")
        return {
            "available": True,
            "state_of_charge_percent": charge,
            "status": str(status.value if isinstance(status, Enum) else status),
            "last_update": updated.isoformat(),
            "capacity_kwh": float(capacity) if capacity is not None else None,
        }

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
