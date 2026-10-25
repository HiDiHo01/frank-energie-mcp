"""Tests for FastMCP registration and service delegation."""

from __future__ import annotations

import logging
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from frank_energie_mcp.server import SERVER_NAME, create_server


def test_server_name() -> None:
    """Keep the MCP server name stable."""
    assert SERVER_NAME == "frank-energie-mcp"


@pytest.mark.asyncio
async def test_registers_all_documented_tools() -> None:
    """Register the complete documented set of 29 MCP tools."""
    server = create_server(AsyncMock())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "get_current_prices",
        "get_today_prices",
        "get_tomorrow_prices",
        "get_gas_price",
        "compare_days",
        "get_average_prices",
        "get_lowest_price",
        "get_highest_price",
        "get_best_split_periods",
        "get_lowest_period",
        "get_highest_period",
        "get_best_start_time",
        "calculate_energy_cost",
        "get_price_threshold_periods",
        "get_negative_price_periods",
        "get_price_trend",
        "calculate_battery_savings",
        "get_charging_cost_breakdown",
        "get_charging_efficiency_analysis",
        "get_charging_power_analysis",
        "get_charging_start_time_analysis",
        "get_charging_deadline_analysis",
        "compare_charging_strategies",
        "get_optimal_charging_schedule",
        "get_price_forecast_summary",
        "get_price_statistics",
        "get_price_volatility",
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

    service.get_current_prices.assert_awaited_once_with(resolution="PT15M")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,service_method",
    [
        ("get_current_prices", "get_current_prices"),
        ("get_today_prices", "get_today_prices"),
        ("get_tomorrow_prices", "get_tomorrow_prices"),
        ("get_gas_price", "get_gas_price"),
        ("get_average_prices", "get_average_prices"),
        ("get_lowest_price", "get_lowest_price"),
        ("get_highest_price", "get_highest_price"),
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

    with (
        caplog.at_level(logging.WARNING, logger="frank_energie_mcp.server"),
        suppress(Exception),
    ):
        await server.call_tool("get_account", {})

    output = caplog.text
    assert "category=ValueError" in output
    for sensitive in (secret, password, customer):
        assert sensitive not in output


@pytest.mark.asyncio
async def test_account_response_excludes_personal_information() -> None:
    """Account output must contain only the explicit public schema."""
    service = AsyncMock()
    service.get_account.return_value = {
        "email": "customer@example.invalid",
        "token": "fake-secret",
        "address": "Example Street 1",
    }
    response = await create_server(service).call_tool("get_account", {})
    rendered = str(response)
    assert "authenticated" in rendered
    for sensitive in ("customer@example.invalid", "fake-secret", "Example Street 1"):
        assert sensitive not in rendered


@pytest.mark.asyncio
async def test_sites_response_excludes_personal_information() -> None:
    """Site output must disclose only the number of sites."""
    service = AsyncMock()
    service.list_sites.return_value = {
        "sites": [{"address": "Example Street 1", "reference": "private-site"}]
    }
    response = await create_server(service).call_tool("list_sites", {})
    rendered = str(response)
    assert "count" in rendered
    assert "Example Street 1" not in rendered
    assert "private-site" not in rendered


@pytest.mark.asyncio
async def test_unknown_sites_structure_is_rejected_without_leaking_data() -> None:
    """Fail closed when the upstream site structure is unrecognized."""
    service = AsyncMock()
    service.list_sites.return_value = {"unexpected": "private-site"}
    try:
        response = await create_server(service).call_tool("list_sites", {})
        rendered = str(response)
    except Exception as exc:
        rendered = str(exc)
    assert "private-site" not in rendered
    assert "Frank Energie request failed" in rendered


@pytest.mark.asyncio
async def test_mcp_price_resolution_parameter() -> None:
    """Allow hourly resolution and reject unsupported values at the tool boundary."""
    service = AsyncMock()
    service.get_current_prices.return_value = {"electricity": None, "gas": None}
    server = create_server(service)
    await server.call_tool("get_current_prices", {"resolution": "PT60M"})
    service.get_current_prices.assert_awaited_once_with(resolution="PT60M")
    with pytest.raises(ToolError, match="validation error"):
        await server.call_tool("get_current_prices", {"resolution": "PT30M"})
    service.get_current_prices.assert_awaited_once_with(resolution="PT60M")


def test_main_starts_local_http_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure Streamable HTTP on loopback without starting a network server."""
    from frank_energie_mcp.server import main

    monkeypatch.setenv("FRANK_ENERGIE_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("FRANK_ENERGIE_MCP_PORT", "8765")
    with patch("frank_energie_mcp.server.create_server") as factory:
        main()
    factory.assert_called_once_with(host="127.0.0.1", port=8765)
    factory.return_value.run.assert_called_once_with(transport="streamable-http")


@pytest.mark.parametrize(
    "host,port",
    [("0.0.0.0", "8000"), ("127.0.0.1", "0"), ("127.0.0.1", "65536"), ("127.0.0.1", "abc")],
)
def test_http_transport_rejects_unsafe_configuration(
    monkeypatch: pytest.MonkeyPatch, host: str, port: str
) -> None:
    """Reject non-loopback binding and invalid ports before server creation."""
    from frank_energie_mcp.server import main

    monkeypatch.setenv("FRANK_ENERGIE_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("FRANK_ENERGIE_MCP_HOST", host)
    monkeypatch.setenv("FRANK_ENERGIE_MCP_PORT", port)
    with patch("frank_energie_mcp.server.create_server") as factory, pytest.raises(ValueError):
        main()
    factory.assert_not_called()


@pytest.mark.parametrize("transport", ["http", "sse", "unknown"])
def test_main_rejects_unsupported_transport(
    monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    """Do not silently start a different network transport."""
    from frank_energie_mcp.server import main

    monkeypatch.setenv("FRANK_ENERGIE_MCP_TRANSPORT", transport)
    with patch("frank_energie_mcp.server.create_server") as factory, pytest.raises(ValueError):
        main()
    factory.assert_not_called()


def test_main_uses_stdio_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the default deployment local and without a listening HTTP port."""
    from frank_energie_mcp.server import main

    monkeypatch.delenv("FRANK_ENERGIE_MCP_TRANSPORT", raising=False)
    with patch("frank_energie_mcp.server.create_server") as factory:
        main()
    factory.assert_called_once_with()
    factory.return_value.run.assert_called_once_with(transport="stdio")
