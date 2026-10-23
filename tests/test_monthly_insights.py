"""Tests for privacy-filtered monthly cost insights."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, site: str | None = "test-site") -> FrankEnergieService:
    """Create a service using an authenticated fake client."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


@pytest.mark.asyncio
async def test_monthly_insights_allowlist() -> None:
    """Return expected/actual costs without invoices or account identifiers."""
    client = AsyncMock()
    client.month_insights.return_value = SimpleNamespace(
        _id="private-id",
        invoiceId="private-invoice",
        expectedCosts=100.0,
        expectedCostsGas=20.0,
        expectedCostsFixed=10.0,
        expectedCostsElectricity=70.0,
        expectedCostsFeedIn=-5.0,
        expectedCostsUntilLastMeterReading=80.0,
        actualCostsUntilLastMeterReading=75.0,
    )
    result = await make_service(client).get_monthly_cost_insights("2026-10")
    assert result == {
        "available": True,
        "month": "2026-10",
        "expectedCosts": 100.0,
        "expectedCostsGas": 20.0,
        "expectedCostsFixed": 10.0,
        "expectedCostsElectricity": 70.0,
        "expectedCostsFeedIn": -5.0,
        "expectedCostsUntilLastMeterReading": 80.0,
        "actualCostsUntilLastMeterReading": 75.0,
    }
    assert "private" not in str(result)
    client.month_insights.assert_awaited_once_with("test-site", "2026-10")


@pytest.mark.asyncio
async def test_monthly_insights_absent_and_invalid_month() -> None:
    """Handle missing insights and reject invalid calendar months."""
    client = AsyncMock()
    client.month_insights.return_value = None
    assert await make_service(client).get_monthly_cost_insights("2026-10") == {
        "available": False,
        "month": "2026-10",
    }
    with pytest.raises(ValueError, match="month"):
        await make_service(client).get_monthly_cost_insights("2026-13")


@pytest.mark.asyncio
async def test_monthly_insights_rejects_nonfinite_values() -> None:
    """Never serialize NaN or infinity in the MCP response."""
    client = AsyncMock()
    client.month_insights.return_value = SimpleNamespace(expectedCosts=float("nan"))
    with pytest.raises(ValueError, match="cost value"):
        await make_service(client).get_monthly_cost_insights("2026-10")


@pytest.mark.asyncio
async def test_monthly_insights_requires_site() -> None:
    """Reject calls without a configured site before contacting the API."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await make_service(client, site=None).get_monthly_cost_insights("2026-10")
    client.month_insights.assert_not_awaited()


@pytest.mark.asyncio
async def test_monthly_insights_mcp_registration() -> None:
    """FastMCP delegates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_monthly_cost_insights", {"month": "2026-10"})
    service.get_monthly_cost_insights.assert_awaited_once_with("2026-10")
