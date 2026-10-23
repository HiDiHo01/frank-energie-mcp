"""Tests for privacy-safe PV operational and steering status."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


class Status(Enum):
    """Mock upstream enum values."""

    ACTIVE = "ACTIVE"


def service_for(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Build an isolated service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_pv_operational_status_filters_private_fields() -> None:
    """Return status and timestamp without the PV device identifier."""
    client = AsyncMock()
    timestamp = datetime(2026, 10, 23, 12, tzinfo=UTC)
    client.smart_pv_system_summary.return_value = SimpleNamespace(
        operational_status=Status.ACTIVE,
        steering_status="ENABLED",
        operational_status_timestamp=timestamp,
        user_id="private",
    )
    assert await service_for(client).get_smart_pv_operational_status("device") == {
        "available": True,
        "operational_status": "ACTIVE",
        "steering_status": "ENABLED",
        "operational_status_timestamp": timestamp.isoformat(),
    }
    client.smart_pv_system_summary.assert_awaited_once_with("device")


@pytest.mark.asyncio
async def test_pv_operational_status_absent_and_invalid() -> None:
    """Preserve absence and reject invalid status fields."""
    client = AsyncMock()
    client.smart_pv_system_summary.return_value = None
    assert await service_for(client).get_smart_pv_operational_status("device") == {
        "available": False
    }
    client.smart_pv_system_summary.return_value = SimpleNamespace(
        operational_status="ACTIVE",
        steering_status="ENABLED",
        operational_status_timestamp=datetime(2026, 10, 23),
    )
    with pytest.raises(ValueError, match="timestamp"):
        await service_for(client).get_smart_pv_operational_status("device")


@pytest.mark.asyncio
async def test_pv_operational_status_auth_and_id() -> None:
    """Reject unauthenticated requests and empty identifiers."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await service_for(client, authenticated=False).get_smart_pv_operational_status("device")
    with pytest.raises(ValueError, match="device_id"):
        await service_for(client).get_smart_pv_operational_status(" ")
    client.smart_pv_system_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_pv_operational_status_mcp_registration() -> None:
    """Verify FastMCP forwards the device ID."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_smart_pv_operational_status", {"device_id": "device"})
    service.get_smart_pv_operational_status.assert_awaited_once_with("device")
