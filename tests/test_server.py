"""Tests for FastMCP registration and service delegation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.server import SERVER_NAME, create_server


def test_server_name() -> None:
    """Keep the MCP server name stable."""
    assert SERVER_NAME == "frank-energie-mcp"


@pytest.mark.asyncio
async def test_registers_six_tools() -> None:
    """Expose all six documented tools."""
    server = create_server(AsyncMock())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "get_current_prices",
        "get_today_prices",
        "get_tomorrow_prices",
        "get_gas_price",
        "get_account",
        "list_sites",
    }


@pytest.mark.asyncio
async def test_current_prices_delegates_to_service() -> None:
    """Invoke the injected service without accessing the external API."""
    service = AsyncMock()
    service.get_current_prices.return_value = {"electricity": []}
    server = create_server(service)

    await server.call_tool("get_current_prices", {})

    service.get_current_prices.assert_awaited_once_with()
