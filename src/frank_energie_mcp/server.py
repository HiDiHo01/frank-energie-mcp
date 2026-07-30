"""MCP server bootstrap for Frank Energie."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tools import (
    get_account,
    get_current_prices,
    get_gas_price,
    get_today_prices,
    get_tomorrow_prices,
    list_sites,
)

DEFAULT_SERVER_NAME = "frank-energie-mcp"


@dataclass(slots=True)
class Server:
    """Represent the MCP server bootstrap.

    The class remains lightweight and only knows how to register callable tool
    handlers. The real MCP transport wiring can be attached later.
    """

    server_name: str = DEFAULT_SERVER_NAME
    _tools: dict[str, Any] = field(default_factory=dict)

    def register_tools(self) -> None:
        """Register the available tool handlers."""
        self._tools = {
            "get_account": get_account,
            "get_current_prices": get_current_prices,
            "get_gas_price": get_gas_price,
            "get_today_prices": get_today_prices,
            "get_tomorrow_prices": get_tomorrow_prices,
            "list_sites": list_sites,
        }

    def run(self) -> int:
        """Run the MCP server entrypoint.

        Returns:
            An integer process exit code.
        """
        self.register_tools()
        print(f"Starting {self.server_name} with {len(self._tools)} tools")
        return 0



def main() -> int:
    """Run the MCP server entrypoint.

    Returns:
        An integer process exit code.
    """
    return Server().run()
