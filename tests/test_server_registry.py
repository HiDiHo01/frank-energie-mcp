"""Tests for the FastMCP tool registry."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from frank_energie_mcp.server import create_server


@pytest.mark.asyncio
async def test_register_tools_populates_all_tools() -> None:
    """The FastMCP registry should include the expected tool names."""
    server = create_server(AsyncMock())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "get_account",
        "get_current_prices",
        "get_gas_price",
        "get_today_prices",
        "get_tomorrow_prices",
        "list_sites",
    }
