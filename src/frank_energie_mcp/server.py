"""FastMCP server bootstrap for Frank Energie."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .library import FrankEnergieService, default_service

SERVER_NAME = "frank-energie-mcp"
_LOGGER = logging.getLogger(__name__)


async def safe_tool_call[T](operation: Callable[[], Awaitable[T]]) -> T:
    """Hide upstream exception details from MCP clients."""
    try:
        return await operation()
    except Exception as exc:
        _LOGGER.warning("MCP tool request failed; category=%s", type(exc).__name__)
        raise ToolError("Frank Energie request failed.") from None


def create_server(service: FrankEnergieService | None = None) -> FastMCP:
    """Create the MCP server and register its read-only tools."""
    server = FastMCP(SERVER_NAME)
    energy_service = service if service is not None else default_service()

    @server.tool()
    async def get_current_prices() -> object:
        """Get today's electricity and gas pricing data."""
        return await safe_tool_call(energy_service.get_current_prices)

    @server.tool()
    async def get_today_prices() -> object:
        """Get today's pricing data."""
        return await safe_tool_call(energy_service.get_today_prices)

    @server.tool()
    async def get_tomorrow_prices() -> object:
        """Get tomorrow's pricing data."""
        return await safe_tool_call(energy_service.get_tomorrow_prices)

    @server.tool()
    async def get_gas_price() -> object:
        """Get today's pricing data including gas prices."""
        return await safe_tool_call(energy_service.get_gas_price)

    @server.tool()
    async def get_account() -> object:
        """Get the authenticated account information."""
        return await safe_tool_call(energy_service.get_account)

    @server.tool()
    async def list_sites() -> object:
        """Get the account data containing delivery sites."""
        return await safe_tool_call(energy_service.list_sites)

    @server.resource("frank-energie://capabilities")
    def capabilities() -> str:
        """Describe available read-only MCP capabilities."""
        return (
            "Read-only Frank Energie market prices are available through "
            "get_current_prices, get_today_prices, get_tomorrow_prices, "
            "and get_gas_price. Account access requires authentication."
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
    """Run the MCP server over standard input and output."""
    create_server().run(transport="stdio")
