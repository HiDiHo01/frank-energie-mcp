"""Tests for the privacy-filtered smart HVAC status MCP tool."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, *, authenticated: bool = True) -> FrankEnergieService:
    """Create a service using an isolated mock client."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="example@invalid.test" if authenticated else None,
            password="test-password" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_hvac_status_returns_only_public_flags() -> None:
    """Discard user identifiers and creation timestamps."""
    client = AsyncMock()
    client.smart_hvac_status.return_value = SimpleNamespace(
        isActivated=True,
        isAvailableInCountry=False,
        userId="private-user-id",
        userCreatedAt="private-created-at",
    )
    result = await make_service(client).get_smart_hvac_status()
    assert result == {
        "available": True,
        "is_activated": True,
        "is_available_in_country": False,
    }
    assert "private" not in str(result)
    client.smart_hvac_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_hvac_status_missing_and_nullable_flags() -> None:
    """Preserve upstream absence and nullable enrollment flags."""
    client = AsyncMock()
    client.smart_hvac_status.return_value = None
    assert await make_service(client).get_smart_hvac_status() == {
        "available": False,
        "is_activated": None,
        "is_available_in_country": None,
    }
    client.smart_hvac_status.return_value = SimpleNamespace(
        isActivated=None, isAvailableInCountry=True
    )
    assert await make_service(client).get_smart_hvac_status() == {
        "available": True,
        "is_activated": None,
        "is_available_in_country": True,
    }


@pytest.mark.asyncio
async def test_hvac_status_rejects_invalid_payload_and_missing_credentials() -> None:
    """Reject malformed flags and unauthenticated calls."""
    client = AsyncMock()
    client.smart_hvac_status.return_value = SimpleNamespace(
        isActivated="yes", isAvailableInCountry=True
    )
    with pytest.raises(ValueError, match="activation flag"):
        await make_service(client).get_smart_hvac_status()
    client.smart_hvac_status.reset_mock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_smart_hvac_status()
    client.smart_hvac_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_hvac_tool_is_registered() -> None:
    """FastMCP delegates to the read-only service method."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_smart_hvac_status", {})
    service.get_smart_hvac_status.assert_awaited_once()
