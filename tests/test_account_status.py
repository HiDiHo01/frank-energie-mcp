"""Contract resolution and feed-in tools expose only allowlisted account flags."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def service_with(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Create a mock-backed service without live account access."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_feed_in_flags_are_allowlisted() -> None:
    """Never return upstream user IDs or enrollment timestamps."""
    client = AsyncMock()
    client.user_smart_feed_in.return_value = SimpleNamespace(
        user_id="secret-id",
        user_created_at="private-timestamp",
        is_activated=True,
        has_accepted_terms=True,
        is_app_onboarding_available=False,
        is_available_in_country=True,
    )
    result = await service_with(client).get_smart_feed_in_status()
    assert result == {
        "available": True,
        "is_activated": True,
        "has_accepted_terms": True,
        "is_app_onboarding_available": False,
        "is_available_in_country": True,
    }
    client.user_smart_feed_in.assert_awaited_once()


@pytest.mark.asyncio
async def test_feed_in_unavailable_and_malformed() -> None:
    """Distinguish absent enrollment from an invalid upstream payload."""
    client = AsyncMock()
    client.user_smart_feed_in.return_value = None
    assert (await service_with(client).get_smart_feed_in_status())["available"] is False
    client.user_smart_feed_in.return_value = SimpleNamespace(is_activated="yes")
    with pytest.raises(ValueError, match="structure"):
        await service_with(client).get_smart_feed_in_status()


@pytest.mark.asyncio
async def test_contract_resolution_read_only() -> None:
    """Expose resolution options but never connection IDs or mutation calls."""
    client = AsyncMock()
    client.contract_price_resolution_state.return_value = SimpleNamespace(
        active_option="PT15M",
        available_options=["PT15M", "PT60M"],
        is_change_request_possible=False,
        customer_name="private",
    )
    result = await service_with(client).get_contract_price_resolution_state("connection")
    assert result == {
        "available": True,
        "active_option": "PT15M",
        "available_options": ["PT15M", "PT60M"],
        "is_change_request_possible": False,
    }
    client.contract_price_resolution_state.assert_awaited_once_with("connection")
    client.contract_price_resolution_request_change.assert_not_awaited()


@pytest.mark.asyncio
async def test_credentials_and_connection_validation() -> None:
    """Fail before making upstream calls for invalid requests."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await service_with(client, authenticated=False).get_smart_feed_in_status()
    with pytest.raises(ValueError, match="connection_id"):
        await service_with(client).get_contract_price_resolution_state(" ")
    client.contract_price_resolution_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_tools_delegate() -> None:
    """Ensure FastMCP exposes both authenticated read operations."""
    mock = AsyncMock()
    server = create_server(mock)
    await server.call_tool("get_smart_feed_in_status", {})
    await server.call_tool(
        "get_contract_price_resolution_state", {"connection_id": "connection"}
    )
    mock.get_smart_feed_in_status.assert_awaited_once()
    mock.get_contract_price_resolution_state.assert_awaited_once_with("connection")
