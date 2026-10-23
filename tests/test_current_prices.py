"""Regression tests for the registered current electricity price MCP tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


@pytest.mark.asyncio
async def test_get_current_prices_returns_public_price_without_login() -> None:
    """Use the public price endpoint and never request account authentication."""
    client = AsyncMock()
    now = datetime.now(UTC)
    active = SimpleNamespace(
        date_from=now - timedelta(minutes=5),
        date_till=now + timedelta(minutes=10),
        total=0.25,
        unit="kWh",
        energy_type="electricity",
    )
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(current_hour=active),
        gas=SimpleNamespace(current_hour=None),
    )
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    server = create_server(service)

    response = await server.call_tool("get_current_prices", {})

    assert "0.25" in str(response)
    assert "kWh" in str(response)
    client.prices.assert_awaited_once()
    client.login.assert_not_awaited()
    client.user_prices.assert_not_awaited()
    client.close.assert_awaited_once()
