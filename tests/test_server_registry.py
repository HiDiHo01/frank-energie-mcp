"""Tests for the server tool registry."""

from __future__ import annotations

from frank_energie_mcp.server import Server


def test_register_tools_populates_all_tools() -> None:
    """The server registry should include the expected tool names."""
    server = Server()
    server.register_tools()

    assert set(server._tools) == {
        "get_account",
        "get_current_prices",
        "get_gas_price",
        "get_today_prices",
        "get_tomorrow_prices",
        "list_sites",
    }
