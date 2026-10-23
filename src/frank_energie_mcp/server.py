"""FastMCP server bootstrap for Frank Energie."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

from .library import FrankEnergieService, PriceResolution, default_service


class AccountResponse(BaseModel):
    """Non-identifying account response."""

    model_config = ConfigDict(extra="forbid", strict=True)
    authenticated: bool = True


class SitesResponse(BaseModel):
    """Non-identifying site summary."""

    model_config = ConfigDict(extra="forbid", strict=True)
    count: int = Field(ge=0)


def _count_sites(data: object) -> int:
    """Accept only recognized site collections."""
    if isinstance(data, (list, tuple)):
        return len(data)
    if isinstance(data, dict):
        for key in ("sites", "deliverySites"):
            value = data.get(key)
            if isinstance(value, (list, tuple)):
                return len(value)
    for key in ("sites", "deliverySites"):
        value = getattr(data, key, None)
        if isinstance(value, (list, tuple)):
            return len(value)
    raise ValueError("Unexpected site response structure.")


SERVER_NAME = "frank-energie-mcp"
_LOGGER = logging.getLogger(__name__)


async def safe_tool_call[T](operation: Callable[[], Awaitable[T]]) -> T:
    """Hide upstream exception details from MCP clients."""
    try:
        return await operation()
    except Exception as exc:
        _LOGGER.warning("MCP tool request failed; category=%s", type(exc).__name__)
        raise ToolError("Frank Energie request failed.") from None


def create_server(
    service: FrankEnergieService | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Create the MCP server and register its read-only tools."""
    server = FastMCP(SERVER_NAME, host=host, port=port)
    energy_service = service if service is not None else default_service()

    @server.tool()
    async def get_current_prices(resolution: PriceResolution = "PT15M") -> object:
        """Get today's electricity and gas pricing data."""
        return await safe_tool_call(
            lambda: energy_service.get_current_prices(resolution=resolution)
        )

    @server.tool()
    async def get_today_prices(resolution: PriceResolution = "PT15M") -> object:
        """Get today's pricing data."""
        return await safe_tool_call(lambda: energy_service.get_today_prices(resolution=resolution))

    @server.tool()
    async def get_tomorrow_prices(resolution: PriceResolution = "PT15M") -> object:
        """Get tomorrow's pricing data."""
        return await safe_tool_call(
            lambda: energy_service.get_tomorrow_prices(resolution=resolution)
        )

    @server.tool()
    async def get_average_prices(
        day: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> object:
        """Average all available electricity and gas total prices for a local date."""
        return await safe_tool_call(
            lambda: energy_service.get_average_prices(day=day, resolution=resolution)
        )

    @server.tool()
    async def get_lowest_price(
        day: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> object:
        """Get the lowest available total-price interval for electricity and gas."""
        return await safe_tool_call(
            lambda: energy_service.get_lowest_price(day=day, resolution=resolution)
        )

    @server.tool()
    async def get_highest_price(
        day: date | None = None, resolution: PriceResolution = "PT15M"
    ) -> object:
        """Get the highest available total-price interval for electricity and gas."""
        return await safe_tool_call(
            lambda: energy_service.get_highest_price(day=day, resolution=resolution)
        )

    @server.tool()
    async def get_lowest_period(
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Find the lowest average total-price consecutive period, e.g. 240 minutes."""
        return await safe_tool_call(
            lambda: energy_service.get_lowest_period(
                period_minutes=period_minutes, day=day, resolution=resolution
            )
        )

    @server.tool()
    async def get_highest_period(
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Find the highest average total-price consecutive period, e.g. 240 minutes."""
        return await safe_tool_call(
            lambda: energy_service.get_highest_period(
                period_minutes=period_minutes, day=day, resolution=resolution
            )
        )

    @server.tool()
    async def get_best_start_time(
        duration_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        earliest_start: datetime | None = None,
        latest_end: datetime | None = None,
    ) -> object:
        """Find the cheapest continuous start time, optionally bounded by timestamps."""
        return await safe_tool_call(
            lambda: energy_service.get_best_start_time(
                duration_minutes, day, resolution, earliest_start, latest_end
            )
        )

    @server.tool()
    async def calculate_energy_cost(
        power_kw: float,
        duration_minutes: int,
        start_time: datetime,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Estimate cost for constant-power electricity usage at a given start time."""
        return await safe_tool_call(
            lambda: energy_service.calculate_energy_cost(
                power_kw, duration_minutes, start_time, resolution
            )
        )

    @server.tool()
    async def get_price_threshold_periods(
        threshold: float,
        below: bool = True,
        minimum_duration_minutes: int = 15,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Find consecutive electricity and gas periods below or above a total price."""
        return await safe_tool_call(
            lambda: energy_service.get_price_threshold_periods(
                threshold, below, minimum_duration_minutes, day, resolution
            )
        )

    @server.tool()
    async def get_best_split_periods(
        total_minutes: int,
        minimum_block_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Select cheapest nonoverlapping fixed-length price blocks."""
        return await safe_tool_call(
            lambda: energy_service.get_best_split_periods(
                total_minutes, minimum_block_minutes, day, resolution
            )
        )

    @server.tool()
    async def calculate_battery_savings(
        capacity_kwh: float,
        charge_power_kw: float,
        discharge_power_kw: float,
        round_trip_efficiency: float,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Estimate idealized one-cycle battery savings from public electricity prices."""
        return await safe_tool_call(
            lambda: energy_service.calculate_battery_savings(
                capacity_kwh,
                charge_power_kw,
                discharge_power_kw,
                round_trip_efficiency,
                day,
                resolution,
            )
        )

    @server.tool()
    async def get_negative_price_periods(
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        minimum_duration_minutes: int = 15,
    ) -> object:
        """Find consecutive negative electricity-price periods."""
        return await safe_tool_call(
            lambda: energy_service.get_negative_price_periods(
                day, resolution, minimum_duration_minutes
            )
        )

    @server.tool()
    async def get_price_trend(
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        stable_tolerance: float = 0.005,
    ) -> object:
        """Classify first-to-last daily price movement."""
        return await safe_tool_call(
            lambda: energy_service.get_price_trend(day, resolution, stable_tolerance)
        )

    @server.tool()
    async def get_price_volatility(
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Return daily spread and consecutive price changes."""
        return await safe_tool_call(lambda: energy_service.get_price_volatility(day, resolution))

    @server.tool()
    async def get_price_statistics(
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Return daily price percentiles and descriptive statistics."""
        return await safe_tool_call(lambda: energy_service.get_price_statistics(day, resolution))

    @server.tool()
    async def compare_days(
        first_day: date,
        second_day: date,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Compare total price distributions for two Amsterdam calendar days."""
        return await safe_tool_call(
            lambda: energy_service.compare_days(first_day, second_day, resolution)
        )

    @server.tool()
    async def get_gas_price(resolution: PriceResolution = "PT15M") -> object:
        """Get today's pricing data including gas prices."""
        return await safe_tool_call(lambda: energy_service.get_gas_price(resolution=resolution))

    @server.tool()
    async def get_smart_battery_fleet_statistics() -> object:
        """Summarize linked battery fleet capacity and rated power."""
        return await safe_tool_call(energy_service.get_smart_battery_fleet_statistics)

    @server.tool()
    async def get_smart_battery_count() -> object:
        """Count linked smart batteries without returning device identifiers."""
        return await safe_tool_call(energy_service.get_smart_battery_count)

    @server.tool()
    async def get_smart_pv_fleet_statistics() -> object:
        """Aggregate linked solar panel groups and declared PV capacity."""
        return await safe_tool_call(energy_service.get_smart_pv_fleet_statistics)

    @server.tool()
    async def get_smart_pv_system_count() -> object:
        """Count linked smart solar PV systems without returning device identifiers."""
        return await safe_tool_call(energy_service.get_smart_pv_system_count)

    @server.tool()
    async def get_electric_vehicle_statistics() -> object:
        """Count linked vehicles, reachable vehicles and smart charging states."""
        return await safe_tool_call(energy_service.get_electric_vehicle_statistics)

    @server.tool()
    async def get_electric_vehicle_count() -> object:
        """Count linked electric vehicles without returning device identifiers."""
        return await safe_tool_call(energy_service.get_electric_vehicle_count)

    @server.tool()
    async def get_smart_hvac_status() -> object:
        """Read smart HVAC activation and country availability without user data."""
        return await safe_tool_call(energy_service.get_smart_hvac_status)

    @server.tool()
    async def get_smart_feed_in_status() -> object:
        """Read privacy-filtered smart feed-in enrollment status."""
        return await safe_tool_call(energy_service.get_smart_feed_in_status)

    @server.tool()
    async def get_contract_price_resolution_state(connection_id: str) -> object:
        """Read contract resolution options without requesting any changes."""
        return await safe_tool_call(
            lambda: energy_service.get_contract_price_resolution_state(connection_id)
        )

    @server.tool()
    async def get_ev_charger_statistics(start_date: date) -> object:
        """Count EV chargers, reachability and smart charging capabilities."""
        return await safe_tool_call(lambda: energy_service.get_ev_charger_statistics(start_date))

    @server.tool()
    async def get_account_country() -> object:
        """Read the account country code without disclosing personal information."""
        return await safe_tool_call(energy_service.get_account_country)

    @server.tool()
    async def get_current_month_cost_summary() -> object:
        """Read current-month expected and actual costs without identifiers."""
        return await safe_tool_call(energy_service.get_current_month_cost_summary)

    @server.tool()
    async def get_monthly_cost_insights(month: str) -> object:
        """Get upstream monthly expected and actual costs without customer metadata."""
        return await safe_tool_call(lambda: energy_service.get_monthly_cost_insights(month))

    @server.tool()
    async def get_period_usage_and_costs(start_date: date) -> object:
        """Read upstream period electricity, gas and feed-in usage and costs."""
        return await safe_tool_call(lambda: energy_service.get_period_usage_and_costs(start_date))

    @server.tool()
    async def get_daily_consumption_statistics(start_date: date, end_date: date) -> object:
        """Aggregate daily meter readings in an inclusive calendar-date range."""
        return await safe_tool_call(
            lambda: energy_service.get_daily_consumption_statistics(start_date, end_date)
        )

    @server.tool()
    async def get_invoice_statistics(year: int) -> object:
        """Aggregate invoice totals for a year without invoice identifiers."""
        return await safe_tool_call(lambda: energy_service.get_invoice_statistics(year))

    @server.tool()
    async def get_smart_pv_system_summary(device_id: str) -> object:
        """Read allowlisted PV system status and totals without identifiers."""
        return await safe_tool_call(lambda: energy_service.get_smart_pv_system_summary(device_id))

    @server.tool()
    async def get_smart_battery_session_statistics(
        device_id: str, start_date: date, end_date: date
    ) -> object:
        """Aggregate battery trading results over an inclusive date range."""
        return await safe_tool_call(
            lambda: energy_service.get_smart_battery_session_statistics(
                device_id, start_date, end_date
            )
        )

    @server.tool()
    async def get_smart_battery_trading_result(device_id: str) -> object:
        """Read the cumulative trading result for one linked smart battery."""
        return await safe_tool_call(
            lambda: energy_service.get_smart_battery_trading_result(device_id)
        )

    @server.tool()
    async def get_smart_battery_status(device_id: str) -> object:
        """Read state of charge, status and capacity of one linked battery."""
        return await safe_tool_call(lambda: energy_service.get_smart_battery_status(device_id))

    @server.tool()
    async def get_account() -> object:
        """Get the authenticated account information."""
        await safe_tool_call(energy_service.get_account)
        return AccountResponse().model_dump(mode="json")

    @server.tool()
    async def list_sites() -> object:
        """Get the account data containing delivery sites."""
        data = await safe_tool_call(energy_service.list_sites)
        try:
            return SitesResponse(count=_count_sites(data)).model_dump(mode="json")
        except ValueError, TypeError:
            raise ToolError("Frank Energie request failed.") from None

    @server.resource("frank-energie://capabilities")
    def capabilities() -> str:
        """Describe available read-only MCP capabilities."""
        return (
            "Read-only Frank Energie market prices are available through "
            "get_current_prices, get_today_prices, get_tomorrow_prices, "
            "get_average_prices, get_lowest_price, get_highest_price, "
            "get_lowest_period, get_highest_period, get_best_start_time, "
            "calculate_energy_cost, get_price_threshold_periods, "
            "get_best_split_periods, calculate_battery_savings, and get_gas_price. "
            "Authenticated device counts are available through "
            "get_smart_battery_count, get_smart_pv_system_count, and "
            "get_electric_vehicle_count. Account access requires authentication."
        )

    @server.prompt()
    def summarize_energy_prices() -> str:
        """Provide a reusable prompt for comparing market prices."""
        return (
            "Call get_today_prices and get_tomorrow_prices. "
            "Compare available electricity and gas market prices, "
            "include units and timestamps, and do not invent missing data."
        )

    return server


def main() -> None:
    """Run stdio by default, or loopback-only Streamable HTTP."""
    transport = os.environ.get("FRANK_ENERGIE_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        create_server().run(transport="stdio")
        return
    if transport != "streamable-http":
        raise ValueError("Unsupported MCP transport; use stdio or streamable-http.")
    host = os.environ.get("FRANK_ENERGIE_MCP_HOST", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("HTTP transport must bind to 127.0.0.1.")
    try:
        port = int(os.environ.get("FRANK_ENERGIE_MCP_PORT", "8000"))
    except ValueError:
        raise ValueError("MCP port must be an integer.") from None
    if not 1 <= port <= 65535:
        raise ValueError("MCP port must be between 1 and 65535.")
    create_server(host=host, port=port).run(transport="streamable-http")
