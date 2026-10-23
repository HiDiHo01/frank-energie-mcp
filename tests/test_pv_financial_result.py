"""Tests for the read-only PV financial result MCP tool."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Build a service with an isolated upstream client."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_pv_financial_result_is_private() -> None:
    """Expose only upstream totals, never device or account metadata."""
    client = AsyncMock()
    client.smart_pv_system_summary.return_value = SimpleNamespace(
        device_id="private-device",
        total_bonus=3.25,
        total_result=-1.5,
        account="private-account",
    )
    assert await make_service(client).get_smart_pv_financial_result("device") == {
        "available": True,
        "total_bonus": 3.25,
        "total_result": -1.5,
    }
    client.smart_pv_system_summary.assert_awaited_once_with("device")


@pytest.mark.asyncio
async def test_pv_financial_result_absent_and_partial() -> None:
    """Handle missing summaries and optional upstream totals."""
    client = AsyncMock()
    client.smart_pv_system_summary.return_value = None
    assert await make_service(client).get_smart_pv_financial_result("device") == {
        "available": False,
        "total_bonus": None,
        "total_result": None,
    }
    client.smart_pv_system_summary.return_value = SimpleNamespace(
        total_bonus=None, total_result=0
    )
    assert await make_service(client).get_smart_pv_financial_result("device") == {
        "available": True,
        "total_bonus": None,
        "total_result": 0.0,
    }


@pytest.mark.asyncio
async def test_pv_financial_result_rejects_invalid_input() -> None:
    """Require credentials, a device ID and finite totals."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_smart_pv_financial_result(
            "device"
        )
    with pytest.raises(ValueError, match="device_id"):
        await make_service(client).get_smart_pv_financial_result(" ")
    client.smart_pv_system_summary.return_value = SimpleNamespace(
        total_bonus=float("inf"), total_result=1.0
    )
    with pytest.raises(ValueError, match="financial result"):
        await make_service(client).get_smart_pv_financial_result("device")


@pytest.mark.asyncio
async def test_pv_financial_result_mcp_registration() -> None:
    """Verify the MCP registration delegates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_smart_pv_financial_result", {"device_id": "device"})
    service.get_smart_pv_financial_result.assert_awaited_once_with("device")
