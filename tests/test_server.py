"""Tests for FastMCP registration and service delegation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.server import SERVER_NAME, create_server


def test_server_name() -> None:
    """Keep the MCP server name stable."""
    assert SERVER_NAME == "frank-energie-mcp"


@pytest.mark.asyncio
async def test_registers_six_tools() -> None:
    """Expose all six documented tools."""
    server = create_server(AsyncMock())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "get_current_prices",
        "get_today_prices",
        "get_tomorrow_prices",
        "get_gas_price",
        "get_account",
        "list_sites",
    }


@pytest.mark.asyncio
async def test_current_prices_delegates_to_service() -> None:
    """Invoke the injected service without accessing the external API."""
    service = AsyncMock()
    service.get_current_prices.return_value = {"electricity": []}
    server = create_server(service)

    await server.call_tool("get_current_prices", {})

    service.get_current_prices.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,service_method",
    [
        ("get_current_prices", "get_current_prices"),
        ("get_today_prices", "get_today_prices"),
        ("get_tomorrow_prices", "get_tomorrow_prices"),
        ("get_gas_price", "get_gas_price"),
        ("get_account", "get_account"),
        ("list_sites", "list_sites"),
    ],
)
async def test_mcp_error_never_exposes_upstream_secrets(
    tool_name: str, service_method: str
) -> None:
    """The serialized MCP tool response must not include upstream exception text."""
    secret = "fake-token-DO-NOT-EXPOSE"
    password = "fake-password-DO-NOT-EXPOSE"
    customer = "customer@example.invalid"
    service = AsyncMock()
    getattr(service, service_method).side_effect = RuntimeError(
        f"Authorization: Bearer {secret}; password={password}; email={customer}"
    )
    server = create_server(service)

    try:
        response = await server.call_tool(tool_name, {})
        rendered = str(response)
    except Exception as exc:
        rendered = str(exc)

    for sensitive in (secret, password, customer):
        assert sensitive not in rendered
    assert "Frank Energie request failed" in rendered


@pytest.mark.asyncio
async def test_upstream_error_does_not_leak_into_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Never log raw upstream exception text, credentials or personal data."""
    secret = "fake-token-DO-NOT-EXPOSE"
    password = "fake-password-DO-NOT-EXPOSE"
    customer = "customer@example.invalid"
    service = AsyncMock()
    service.get_account.side_effect = ValueError(
        f"token={secret} password={password} email={customer}"
    )
    server = create_server(service)

    with caplog.at_level(logging.WARNING, logger="frank_energie_mcp.server"):
        try:
            await server.call_tool("get_account", {})
        except Exception:
            pass

    output = caplog.text
    assert "category=ValueError" in output
    for sensitive in (secret, password, customer):
        assert sensitive not in output
