"""Tests for smart battery fleet statistics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Build an isolated authenticated service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_battery_fleet_statistics_and_privacy() -> None:
    """Aggregate non-null capacity and power without revealing device metadata."""
    client = AsyncMock()
    client.smart_batteries.return_value = SimpleNamespace(
        batteries=[
            SimpleNamespace(
                id="private-one",
                capacity=5.0,
                max_charge_power=2.5,
                max_discharge_power=2.0,
            ),
            SimpleNamespace(
                id="private-two",
                capacity=None,
                max_charge_power=None,
                max_discharge_power=3.0,
            ),
        ]
    )
    result = await make_service(client).get_smart_battery_fleet_statistics()
    assert result == {
        "battery_count": 2,
        "capacity_reported_count": 1,
        "total_capacity_kwh": 5.0,
        "total_max_charge_power": 2.5,
        "total_max_discharge_power": 5.0,
    }
    assert "private" not in str(result)


@pytest.mark.asyncio
async def test_battery_fleet_absent_and_invalid() -> None:
    """Preserve unknown capacity instead of inventing a zero total."""
    client = AsyncMock()
    client.smart_batteries.return_value = SimpleNamespace(batteries=[])
    result = await make_service(client).get_smart_battery_fleet_statistics()
    assert result["battery_count"] == 0
    assert result["total_capacity_kwh"] is None
    client.smart_batteries.return_value = SimpleNamespace(
        batteries=[SimpleNamespace(capacity=float("inf"), max_charge_power=1.0)]
    )
    with pytest.raises(ValueError, match="capacity or power"):
        await make_service(client).get_smart_battery_fleet_statistics()


@pytest.mark.asyncio
async def test_battery_fleet_requires_credentials() -> None:
    """Do not query linked batteries without authentication."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_smart_battery_fleet_statistics()
    client.smart_batteries.assert_not_awaited()


@pytest.mark.asyncio
async def test_battery_fleet_tool_registration() -> None:
    """Verify FastMCP delegates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_smart_battery_fleet_statistics", {})
    service.get_smart_battery_fleet_statistics.assert_awaited_once_with()
