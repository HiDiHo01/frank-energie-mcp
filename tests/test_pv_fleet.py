"""Tests for privacy-filtered smart PV fleet statistics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Build a service backed by an isolated upstream mock."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_pv_fleet_statistics_and_privacy() -> None:
    """Aggregate declared panel counts and capacity without exposing identifiers."""
    client = AsyncMock()
    client.smart_pv_systems.return_value = SimpleNamespace(
        systems=[
            SimpleNamespace(
                id="private-system",
                panel_groups=[
                    SimpleNamespace(id="private-group", panel_count=8, capacity_kwp=3.2),
                    SimpleNamespace(id="private-group-two", panel_count=None, capacity_kwp=1.5),
                ],
            )
        ]
    )
    result = await make_service(client).get_smart_pv_fleet_statistics()
    assert result == {
        "system_count": 1,
        "panel_group_count": 2,
        "panel_count_reported_groups": 1,
        "total_panel_count": 8,
        "capacity_reported_groups": 2,
        "total_capacity_kwp": 4.7,
    }
    assert "private" not in str(result)
    client.smart_pv_systems.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_pv_fleet_missing_and_invalid() -> None:
    """Preserve missing capacity and reject malformed numeric values."""
    client = AsyncMock()
    client.smart_pv_systems.return_value = SimpleNamespace(systems=[])
    result = await make_service(client).get_smart_pv_fleet_statistics()
    assert result["system_count"] == 0
    assert result["total_capacity_kwp"] is None
    client.smart_pv_systems.return_value = SimpleNamespace(
        systems=[
            SimpleNamespace(
                panel_groups=[SimpleNamespace(panel_count=-1, capacity_kwp=1.0)]
            )
        ]
    )
    with pytest.raises(ValueError, match="panel count"):
        await make_service(client).get_smart_pv_fleet_statistics()


@pytest.mark.asyncio
async def test_pv_fleet_requires_credentials() -> None:
    """Reject unauthenticated access without querying upstream."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_smart_pv_fleet_statistics()
    client.smart_pv_systems.assert_not_awaited()


@pytest.mark.asyncio
async def test_pv_fleet_mcp_registration() -> None:
    """Verify FastMCP delegates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_smart_pv_fleet_statistics", {})
    service.get_smart_pv_fleet_statistics.assert_awaited_once_with()
