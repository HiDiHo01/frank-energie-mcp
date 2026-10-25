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
    async def get_best_start_time(
        period_minutes: int,
        day: date | None = None,
        resolution: PriceResolution = "PT15M",
        consumption_kwh: float | None = None,
    ) -> object:
        """Find the cheapest electricity start time and optional estimated cost."""
        return await safe_tool_call(
            lambda: energy_service.get_best_start_time(
                period_minutes=period_minutes,
                day=day,
                resolution=resolution,
                consumption_kwh=consumption_kwh,
            )
        )

    @server.tool()
    async def calculate_energy_cost(
        start: datetime,
        end: datetime,
        consumption_kwh: float,
        resolution: PriceResolution = "PT15M",
    ) -> object:
        """Estimate electricity cost over a fully priced time range."""
        return await safe_tool_call(
            lambda: energy_service.calculate_energy_cost(
                start=start,
                end=end,
                consumption_kwh=consumption_kwh,
                resolution=resolution,
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
    async def get_gas_price(resolution: PriceResolution = "PT15M") -> object:
        """Get today's pricing data including gas prices."""
        return await safe_tool_call(lambda: energy_service.get_gas_price(resolution=resolution))

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
            "get_lowest_period, get_highest_period, get_best_start_time, and get_gas_price. "
            "Account access requires authentication."
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
