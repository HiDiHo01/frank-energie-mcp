"""Tests for privacy-filtered electric vehicle fleet statistics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Construct a service with an isolated upstream mock."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_vehicle_statistics_and_privacy() -> None:
    """Return aggregate connectivity flags without vehicle IDs."""
    client = AsyncMock()
    client.enode_vehicles.return_value = SimpleNamespace(
        vehicles=[
            SimpleNamespace(
                id="private-vehicle",
                is_reachable=True,
                can_smart_charge=True,
                charge_settings=SimpleNamespace(is_smart_charging_enabled=True),
            ),
            SimpleNamespace(
                id="private-vehicle-two",
                is_reachable=False,
                can_smart_charge=True,
                charge_settings=SimpleNamespace(is_smart_charging_enabled=False),
            ),
        ]
    )
    result = await make_service(client).get_electric_vehicle_statistics()
    assert result == {
        "vehicle_count": 2,
        "reachable_count": 1,
        "smart_capable_count": 2,
        "smart_enabled_count": 1,
    }
    assert "private" not in str(result)
    client.enode_vehicles.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_vehicle_statistics_missing_and_invalid() -> None:
    """Handle absent collections and reject malformed flags."""
    client = AsyncMock()
    client.enode_vehicles.return_value = None
    assert (await make_service(client).get_electric_vehicle_statistics())[
        "vehicle_count"
    ] == 0
    client.enode_vehicles.return_value = SimpleNamespace(
        vehicles=[
            SimpleNamespace(
                is_reachable="yes",
                can_smart_charge=True,
                charge_settings=SimpleNamespace(is_smart_charging_enabled=True),
            )
        ]
    )
    with pytest.raises(ValueError, match="capability flags"):
        await make_service(client).get_electric_vehicle_statistics()


@pytest.mark.asyncio
async def test_vehicle_statistics_require_credentials() -> None:
    """Reject unauthenticated access before contacting upstream."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_electric_vehicle_statistics()
    client.enode_vehicles.assert_not_awaited()


@pytest.mark.asyncio
async def test_vehicle_statistics_tool_registration() -> None:
    """Verify FastMCP delegates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_electric_vehicle_statistics", {})
    service.get_electric_vehicle_statistics.assert_awaited_once_with()
