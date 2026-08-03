"""MCP server bootstrap for Frank Energie."""

from __future__ import annotations

from typing import Final

DEFAULT_SERVER_NAME: Final[str] = "frank-energie-mcp"


class Server:
    """MCP server for Frank Energie."""

    def __init__(self) -> None:
        """Initialize the server."""
        self._tools: dict[str, callable] = {}

    def register_tools(self) -> None:
        """Register all available tools."""
        self._tools = {
            "get_account": None,
            "get_current_prices": None,
            "get_gas_price": None,
            "get_today_prices": None,
            "get_tomorrow_prices": None,
            "list_sites": None,
        }


def main() -> int:
    """Run the MCP server entrypoint.

    Returns:
        An integer process exit code.
    """
    print(f"Starting {DEFAULT_SERVER_NAME}")
    return 0
