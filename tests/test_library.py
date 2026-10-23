"""Regression tests for the FastMCP server and library bridge."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


@pytest.fixture
def client() -> AsyncMock:
    """Provide a mocked asynchronous upstream client."""
    instance = AsyncMock()
    instance.prices.return_value = {"electricity": []}
    instance.UserSites.return_value = {"sites": []}
    return instance


@pytest.fixture
def service(client: AsyncMock) -> FrankEnergieService:
    """Provide a service with a mockable upstream factory."""
    return FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))


@pytest.mark.asyncio
async def test_today_prices_uses_single_date(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Ensure the bridge uses the upstream single-date API."""
    assert await service.get_today_prices() == {"electricity": []}
    assert isinstance(client.prices.await_args.args[0], date)
    assert len(client.prices.await_args.args) == 1
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_sites_uses_upstream_user_sites(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Ensure delivery sites are requested through the dedicated endpoint."""
    assert await service.list_sites() == {"sites": []}
    client.UserSites.assert_awaited_once_with()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_server_registers_tools_resources_and_prompts(
    service: FrankEnergieService,
) -> None:
    """Verify FastMCP exposes the declared read-only interface."""
    server = create_server(service)
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "get_current_prices",
        "get_today_prices",
        "get_tomorrow_prices",
        "get_gas_price",
        "get_account",
        "list_sites",
    }
    resources = await server.list_resources()
    assert any(str(resource.uri) == "frank-energie://capabilities" for resource in resources)
    prompts = await server.list_prompts()
    assert any(prompt.name == "summarize_energy_prices" for prompt in prompts)


@pytest.mark.asyncio
async def test_gas_prices_uses_single_date(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Prevent regression to the unsupported two-date API call."""
    await service.get_gas_price()
    assert len(client.prices.await_args.args) == 1
    assert isinstance(client.prices.await_args.args[0], date)
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_tomorrow_prices_uses_single_date(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Use the upstream single-date price API for tomorrow."""
    await service.get_tomorrow_prices()
    assert len(client.prices.await_args.args) == 1
    assert isinstance(client.prices.await_args.args[0], date)
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_closes_after_upstream_failure(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Close the upstream session even when the request fails."""
    client.prices.side_effect = RuntimeError("Simulated upstream failure")
    with pytest.raises(RuntimeError, match="Simulated upstream failure"):
        await service.get_today_prices()
    client.close.assert_awaited_once()
