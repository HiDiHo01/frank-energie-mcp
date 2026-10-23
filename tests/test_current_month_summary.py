"""Tests for the current month cost summary MCP tool."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, site: str | None = "site") -> FrankEnergieService:
    """Build a service with fake credentials and a mocked upstream API."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


@pytest.mark.asyncio
async def test_month_summary_privacy_and_values() -> None:
    """Allowlist costs and completeness without leaking invoice metadata."""
    client = AsyncMock()
    client.month_summary.return_value = SimpleNamespace(
        _id="private-id",
        lastMeterReadingDate="2026-10-10",
        actualCostsUntilLastMeterReadingDate=12.5,
        expectedCostsUntilLastMeterReadingDate=13.5,
        expectedCosts=40.0,
        expectedCostsPerDay=1.3,
        meterReadingDayCompleteness=0.9,
        gasExcluded=False,
    )
    result = await make_service(client).get_current_month_cost_summary()
    assert result == {
        "available": True,
        "actualCostsUntilLastMeterReadingDate": 12.5,
        "expectedCostsUntilLastMeterReadingDate": 13.5,
        "expectedCosts": 40.0,
        "expectedCostsPerDay": 1.3,
        "meterReadingDayCompleteness": 0.9,
        "gas_excluded": False,
    }
    assert "private" not in str(result)
    client.month_summary.assert_awaited_once_with("site")


@pytest.mark.asyncio
async def test_month_summary_unavailable_and_invalid() -> None:
    """Preserve absence and reject nonfinite values."""
    client = AsyncMock()
    client.month_summary.return_value = None
    assert await make_service(client).get_current_month_cost_summary() == {
        "available": False
    }
    client.month_summary.return_value = SimpleNamespace(expectedCosts=float("inf"))
    with pytest.raises(ValueError, match="summary value"):
        await make_service(client).get_current_month_cost_summary()


@pytest.mark.asyncio
async def test_month_summary_requires_site() -> None:
    """Reject missing delivery site without contacting upstream."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await make_service(client, site=None).get_current_month_cost_summary()
    client.month_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_month_summary_mcp_registration() -> None:
    """Verify FastMCP dispatches to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_current_month_cost_summary", {})
    service.get_current_month_cost_summary.assert_awaited_once_with()
