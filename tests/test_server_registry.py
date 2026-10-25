"""Tests for the FastMCP tool registry."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.server import create_server


@pytest.mark.asyncio
async def test_register_tools_populates_all_tools() -> None:
    """The FastMCP registry should include the expected tool names."""
    server = create_server(AsyncMock())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "get_account",
        "get_average_prices",
        "get_highest_period",
        "get_best_start_time",
        "calculate_energy_cost",
        "get_price_threshold_periods",
        "get_negative_price_periods",
        "get_price_trend",
        "get_price_volatility",
        "get_highest_price",
        "get_lowest_period",
        "get_lowest_price",
        "get_current_prices",
        "get_gas_price",
        "get_today_prices",
        "get_tomorrow_prices",
        "list_sites",
    }
