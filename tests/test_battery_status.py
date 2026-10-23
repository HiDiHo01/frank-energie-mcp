"""Read-only smart battery status tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock) -> FrankEnergieService:
    """Provide a credentialed, mock-backed upstream session."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
        )
    )


@pytest.mark.asyncio
async def test_battery_status_is_allowlisted() -> None:
    """Do not return device identifiers or trading settings."""
    client = AsyncMock()
    client.smart_battery_details.return_value = SimpleNamespace(
        smart_battery=SimpleNamespace(
            id="private-id", capacity=5.0, settings={"private": True}
        ),
        smart_battery_summary=SimpleNamespace(
            last_known_state_of_charge=72,
            last_known_status="CHARGING",
            last_update=datetime(2026, 10, 23, tzinfo=UTC),
        ),
    )
    result = await make_service(client).get_smart_battery_status("device")
    assert result == {
        "available": True,
        "state_of_charge_percent": 72,
        "status": "CHARGING",
        "last_update": "2026-10-23T00:00:00+00:00",
        "capacity_kwh": 5.0,
    }
    assert "private" not in str(result)
    client.smart_battery_details.assert_awaited_once_with("device")


@pytest.mark.asyncio
async def test_battery_status_missing_and_invalid() -> None:
    """Represent absent devices and reject invalid upstream charge readings."""
    client = AsyncMock()
    client.smart_battery_details.return_value = None
    assert await make_service(client).get_smart_battery_status("device") == {
        "available": False
    }
    with pytest.raises(ValueError, match="device_id"):
        await make_service(client).get_smart_battery_status(" ")
    client.smart_battery_details.return_value = SimpleNamespace(
        smart_battery=SimpleNamespace(capacity=5.0),
        smart_battery_summary=SimpleNamespace(
            last_known_state_of_charge=150,
            last_known_status="CHARGING",
            last_update=datetime.now(UTC),
        ),
    )
    with pytest.raises(ValueError, match="state of charge"):
        await make_service(client).get_smart_battery_status("device")


@pytest.mark.asyncio
async def test_battery_mcp_registration() -> None:
    """Ensure FastMCP delegates the device ID to the service."""
    mock = AsyncMock()
    server = create_server(mock)
    await server.call_tool("get_smart_battery_status", {"device_id": "device"})
    mock.get_smart_battery_status.assert_awaited_once_with("device")
