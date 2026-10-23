"""Tests for the privacy-filtered smart battery trading result."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Create a service with a mocked upstream client."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_trading_result_excludes_identifiers() -> None:
    """Only the upstream cumulative result is returned."""
    client = AsyncMock()
    client.smart_battery_details.return_value = SimpleNamespace(
        device_id="private-device",
        smart_battery_summary=SimpleNamespace(total_result=-12.5, user_id="private-user"),
    )
    result = await make_service(client).get_smart_battery_trading_result("device")
    assert result == {"available": True, "total_result": -12.5}
    client.smart_battery_details.assert_awaited_once_with("device")


@pytest.mark.asyncio
async def test_trading_result_absent_and_invalid() -> None:
    """Preserve absence and reject invalid totals."""
    client = AsyncMock()
    client.smart_battery_details.return_value = None
    assert await make_service(client).get_smart_battery_trading_result("device") == {
        "available": False,
        "total_result": None,
    }
    client.smart_battery_details.return_value = SimpleNamespace(
        smart_battery_summary=SimpleNamespace(total_result=float("nan"))
    )
    with pytest.raises(ValueError, match="trading result"):
        await make_service(client).get_smart_battery_trading_result("device")


@pytest.mark.asyncio
async def test_trading_result_auth_and_id_validation() -> None:
    """Reject unauthenticated or blank device requests."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_smart_battery_trading_result(
            "device"
        )
    with pytest.raises(ValueError, match="device_id"):
        await make_service(client).get_smart_battery_trading_result(" ")
    client.smart_battery_details.assert_not_awaited()


@pytest.mark.asyncio
async def test_trading_result_tool_registration() -> None:
    """Verify FastMCP dispatches the device ID."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_smart_battery_trading_result", {"device_id": "device"})
    service.get_smart_battery_trading_result.assert_awaited_once_with("device")
