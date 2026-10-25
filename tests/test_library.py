"""Regression tests for the FastMCP server and library bridge."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import (
    FrankEnergieLibraryBridge,
    FrankEnergieService,
    PriceResolution,
)
from frank_energie_mcp.server import create_server


@pytest.fixture
def client() -> AsyncMock:
    """Provide a mocked asynchronous upstream client."""
    instance = AsyncMock()
    instance.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=[]),
        gas=SimpleNamespace(price_data=[]),
    )
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
    assert await service.get_today_prices() == {"electricity": [], "gas": []}
    assert isinstance(client.prices.await_args.args[0], date)
    assert len(client.prices.await_args.args) == 1
    assert client.prices.await_args.kwargs == {"resolution": "PT15M"}
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_sites_uses_upstream_user_sites(client: AsyncMock) -> None:
    """Ensure delivery sites are requested through the dedicated endpoint."""
    service = FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="test@example.invalid",
            password="dummy-test-password",
        )
    )
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
        "compare_days",
        "get_average_prices",
        "get_lowest_price",
        "get_highest_price",
        "get_best_split_periods",
        "get_lowest_period",
        "get_highest_period",
        "get_best_start_time",
        "calculate_energy_cost",
        "get_price_threshold_periods",
        "get_negative_price_periods",
        "get_price_trend",
        "calculate_battery_savings",
        "get_optimal_charging_schedule",
        "get_price_forecast_summary",
        "get_price_statistics",
        "get_price_volatility",
        "get_account",
        "list_sites",
    }
    resources = await server.list_resources()
    assert any(str(resource.uri) == "frank-energie://capabilities" for resource in resources)
    prompts = await server.list_prompts()
    assert any(prompt.name == "summarize_energy_prices" for prompt in prompts)


@pytest.mark.asyncio
async def test_gas_prices_uses_single_date(service: FrankEnergieService, client: AsyncMock) -> None:
    """Prevent regression to the unsupported two-date API call."""
    client.prices.return_value = SimpleNamespace(gas=SimpleNamespace(current_hour=None))
    assert await service.get_gas_price() is None
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


@pytest.mark.asyncio
async def test_current_prices_selects_upstream_active_records(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Return the upstream active price instead of the full day's series."""
    start = datetime.now(UTC)
    active = SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(minutes=15),
        total=0.25,
        unit="kWh",
        energy_type="electricity",
    )
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(current_hour=active),
        gas=SimpleNamespace(current_hour=None),
    )

    result = await service.get_current_prices()

    assert datetime.fromisoformat(result["electricity"]["date_from"]) == start
    assert datetime.fromisoformat(result["electricity"]["date_till"]) == start + timedelta(
        minutes=15
    )
    assert result["electricity"]["total"] == 0.25
    assert result["electricity"]["unit"] == "kWh"
    assert result["electricity"]["energy_type"] == "electricity"
    assert result["gas"] is None
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_authenticated_account_uses_configured_site(client: AsyncMock) -> None:
    """Authenticate before retrieving account data for the configured site."""
    bridge = FrankEnergieLibraryBridge(
        factory=lambda: client,
        username="test@example.invalid",
        password="dummy-test-password",
        site_reference="test-site",
    )
    service = FrankEnergieService(bridge)
    client.user.return_value = {"id": "synthetic-account"}

    assert await service.get_account() == {"id": "synthetic-account"}
    client.login.assert_awaited_once_with("test@example.invalid", "dummy-test-password")
    client.user.assert_awaited_once_with("test-site")
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_missing_site_does_not_start_session(client: AsyncMock) -> None:
    """Reject missing site configuration before accessing upstream services."""
    service = FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="test@example.invalid",
            password="dummy-test-password",
        )
    )
    with pytest.raises(RuntimeError, match="FRANK_ENERGIE_SITE_REFERENCE"):
        await service.get_account()
    client.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_failure_closes_session(client: AsyncMock) -> None:
    """Always close the upstream client when login fails."""
    client.login.side_effect = RuntimeError("Simulated login failure")
    service = FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="test@example.invalid",
            password="dummy-test-password",
        )
    )
    with pytest.raises(RuntimeError, match="Simulated login failure"):
        await service.get_today_prices()
    client.prices.assert_not_awaited()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_sites_require_credentials(client: AsyncMock) -> None:
    """Do not send an unauthenticated site request."""
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    with pytest.raises(RuntimeError, match="requires Frank Energie credentials"):
        await service.list_sites()
    client.UserSites.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_prices_without_credentials_uses_public_endpoint(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Public electricity prices must work without logging into an account."""
    start = datetime.now(UTC)
    active = SimpleNamespace(
        date_from=start,
        date_till=start + timedelta(hours=1),
        total=0.21,
        unit="kWh",
        energy_type="electricity",
    )
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(current_hour=active),
        gas=SimpleNamespace(current_hour=None),
    )

    result = await service.get_current_prices()

    assert result["electricity"]["total"] == 0.21
    assert result["electricity"]["unit"] == "kWh"
    client.login.assert_not_awaited()
    client.user_prices.assert_not_awaited()
    client.user.assert_not_awaited()
    client.UserSites.assert_not_awaited()
    client.prices.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_current_prices_prefers_api_per_unit_over_optional_unit(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """The upstream Price model populates per_unit from GraphQL perUnit."""
    now = datetime.now(UTC)
    active = SimpleNamespace(
        date_from=now,
        date_till=now + timedelta(minutes=15),
        total=0.25,
        unit=None,
        per_unit="kWh",
        energy_type="electricity",
    )
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(current_hour=active),
        gas=SimpleNamespace(current_hour=None),
    )

    result = await service.get_current_prices()

    assert result["electricity"]["unit"] == "kWh"


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["PT15M", "PT60M"])
async def test_requested_resolution_reaches_upstream(
    service: FrankEnergieService, client: AsyncMock, resolution: PriceResolution
) -> None:
    """Forward the requested resolution unchanged to the upstream library."""
    await service.get_today_prices(resolution=resolution)
    assert client.prices.await_args.kwargs == {"resolution": resolution}


@pytest.mark.asyncio
async def test_today_prices_serializes_public_intervals(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Normalize upstream intervals to JSON without leaking extra fields."""
    now = datetime.now(UTC)
    entry = SimpleNamespace(
        date_from=now,
        date_till=now + timedelta(minutes=15),
        total=0.25,
        per_unit="kWh",
        energy_type="electricity",
        authToken="do-not-expose",
    )
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=[entry]),
        gas=SimpleNamespace(price_data=[]),
    )
    result = await service.get_today_prices()
    assert result["electricity"][0]["total"] == 0.25
    assert result["electricity"][0]["unit"] == "kWh"
    assert datetime.fromisoformat(result["electricity"][0]["date_from"]) == now
    assert "authToken" not in result["electricity"][0]


@pytest.mark.asyncio
async def test_today_prices_rejects_unbounded_series(
    service: FrankEnergieService, client: AsyncMock
) -> None:
    """Reject unexpectedly large upstream responses before serializing."""
    client.prices.return_value = SimpleNamespace(
        electricity=SimpleNamespace(price_data=[None] * 201),
        gas=SimpleNamespace(price_data=[]),
    )
    with pytest.raises(ValueError, match="Invalid market-price series"):
        await service.get_today_prices()
