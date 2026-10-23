"""FastMCP server bootstrap for Frank Energie."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .library import FrankEnergieService, default_service

SERVER_NAME = "frank-energie-mcp"


def create_server(service: FrankEnergieService | None = None) -> FastMCP:
    """Create the MCP server and register its read-only tools."""
    server = FastMCP(SERVER_NAME)
    energy_service = service if service is not None else default_service()

    @server.tool()
    async def get_current_prices() -> object:
        """Get today's electricity and gas pricing data."""
        return await energy_service.get_current_prices()

    @server.tool()
    async def get_today_prices() -> object:
        """Get today's pricing data."""
        return await energy_service.get_today_prices()

    @server.tool()
    async def get_tomorrow_prices() -> object:
        """Get tomorrow's pricing data."""
        return await energy_service.get_tomorrow_prices()

    @server.tool()
    async def get_gas_price() -> object:
        """Get today's pricing data including gas prices."""
        return await energy_service.get_gas_price()

    @server.tool()
    async def get_account() -> object:
        """Get the authenticated account information."""
        return await energy_service.get_account()

    @server.tool()
    async def list_sites() -> object:
        """Get the account data containing delivery sites."""
        return await energy_service.list_sites()

    return server


def main() -> None:
    """Run the MCP server over standard input and output."""
    create_server().run(transport="stdio")
