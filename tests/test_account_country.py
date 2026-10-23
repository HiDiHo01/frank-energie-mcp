"""Tests for privacy-filtered authenticated account country."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, authenticated: bool = True) -> FrankEnergieService:
    """Construct an isolated upstream service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid" if authenticated else None,
            password="placeholder" if authenticated else None,
        )
    )


@pytest.mark.asyncio
async def test_account_country_excludes_personal_data() -> None:
    """Return only the country code from the upstream Me model."""
    client = AsyncMock()
    client.user_country.return_value = SimpleNamespace(
        countryCode="NL", email="private@example.invalid", id="private-id"
    )
    result = await make_service(client).get_account_country()
    assert result == {"country_code": "NL"}
    assert "private" not in str(result)
    client.user_country.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_account_country_rejects_invalid_values() -> None:
    """Reject malformed or unexpected upstream country codes."""
    client = AsyncMock()
    client.user_country.return_value = SimpleNamespace(countryCode="Netherlands")
    with pytest.raises(ValueError, match="country code"):
        await make_service(client).get_account_country()


@pytest.mark.asyncio
async def test_account_country_requires_credentials() -> None:
    """Do not call upstream account endpoints without credentials."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="credentials"):
        await make_service(client, authenticated=False).get_account_country()
    client.user_country.assert_not_awaited()


@pytest.mark.asyncio
async def test_account_country_tool_registration() -> None:
    """Verify the FastMCP tool delegates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_account_country", {})
    service.get_account_country.assert_awaited_once_with()
