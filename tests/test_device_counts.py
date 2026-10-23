"""Privacy boundaries and API delegation for linked-device tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "field", "tool"),
    [
        ("smart_batteries", "batteries", "get_smart_battery_count"),
        ("smart_pv_systems", "systems", "get_smart_pv_system_count"),
        ("enode_vehicles", "vehicles", "get_electric_vehicle_count"),
    ],
)
async def test_linked_device_counts_are_private(
    method: str, field: str, tool: str
) -> None:
    """Count only; do not expose raw device metadata or identifiers."""
    client = AsyncMock()
    private_device = SimpleNamespace(id="sensitive-device-id", address="private-address")
    getattr(client, method).return_value = SimpleNamespace(**{field: [private_device]})
    service = FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client, username="test@example.invalid", password="fake"
        )
    )
    result = await getattr(service, tool)()
    assert result == {"count": 1}
    assert "sensitive" not in str(result)
    getattr(client, method).assert_awaited_once()
    client.login.assert_awaited_once_with("test@example.invalid", "fake")
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_credentials_rejected_before_upstream_call() -> None:
    """Prevent unauthenticated account requests."""
    client = AsyncMock()
    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=lambda: client))
    with pytest.raises(RuntimeError, match="credentials"):
        await service.get_smart_battery_count()
    client.smart_batteries.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrecognized_collection_rejected() -> None:
    """Fail closed instead of serializing an unexpected upstream response."""
    client = AsyncMock()
    client.smart_pv_systems.return_value = SimpleNamespace(systems={"id": "secret"})
    service = FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client, username="test@example.invalid", password="fake"
        )
    )
    with pytest.raises(ValueError, match="collection"):
        await service.get_smart_pv_system_count()


@pytest.mark.asyncio
async def test_fastmcp_device_count_delegation() -> None:
    """Verify that all three device tools are registered and callable."""
    service = AsyncMock()
    server = create_server(service)
    for name in (
        "get_smart_battery_count",
        "get_smart_pv_system_count",
        "get_electric_vehicle_count",
    ):
        getattr(service, name).return_value = {"count": 2}
        await server.call_tool(name, {})
        getattr(service, name).assert_awaited_once()
