"""Regression tests for upstream monthly actual-versus-expected usage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def service_for(client: AsyncMock, site: str | None = "site") -> FrankEnergieService:
    """Construct an isolated authenticated service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


def difference(unit: str = "kWh", actual: float = 4.0) -> SimpleNamespace:
    """Construct an upstream difference model with no identifiers."""
    return SimpleNamespace(
        unit=unit,
        actualUsage=actual,
        actualAverageUnitPrice=0.3,
        actualCosts=1.2,
        expectedUsage=5.0,
        expectedAverageUnitPrice=0.2,
        expectedCosts=1.0,
        private_id="never-expose",
    )


@pytest.mark.asyncio
async def test_monthly_usage_differences_are_allowlisted() -> None:
    """Preserve upstream category metrics without personal data."""
    client = AsyncMock()
    client.month_insights.return_value = SimpleNamespace(
        electricityDifference=difference(),
        gasDifference=difference("m3", 2.0),
        feedInDifference=None,
        account_id="secret",
    )
    result = await service_for(client).get_monthly_usage_differences("2026-10")
    assert result["available"] is True
    assert result["month"] == "2026-10"
    assert result["electricity"] == {
        "unit": "kWh",
        "actualUsage": 4.0,
        "actualAverageUnitPrice": 0.3,
        "actualCosts": 1.2,
        "expectedUsage": 5.0,
        "expectedAverageUnitPrice": 0.2,
        "expectedCosts": 1.0,
    }
    assert result["gas"]["unit"] == "m3"
    assert result["feed_in"] is None
    assert "account_id" not in str(result)
    client.month_insights.assert_awaited_once_with("site", "2026-10")


@pytest.mark.asyncio
async def test_monthly_usage_absent_and_invalid() -> None:
    """Handle missing data and reject invalid upstream values."""
    client = AsyncMock()
    client.month_insights.return_value = None
    assert await service_for(client).get_monthly_usage_differences("2026-10") == {
        "available": False,
        "month": "2026-10",
    }
    client.month_insights.return_value = SimpleNamespace(
        electricityDifference=difference(actual=float("inf")),
        gasDifference=None,
        feedInDifference=None,
    )
    with pytest.raises(ValueError, match="usage difference"):
        await service_for(client).get_monthly_usage_differences("2026-10")


@pytest.mark.asyncio
async def test_monthly_usage_input_validation() -> None:
    """Reject malformed months and absent site references."""
    client = AsyncMock()
    with pytest.raises(ValueError, match="month"):
        await service_for(client).get_monthly_usage_differences("2026-13")
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await service_for(client, site=None).get_monthly_usage_differences("2026-10")
    client.month_insights.assert_not_awaited()


@pytest.mark.asyncio
async def test_monthly_usage_tool_registration() -> None:
    """Verify the FastMCP wrapper forwards the month argument."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_monthly_usage_differences", {"month": "2026-10"})
    service.get_monthly_usage_differences.assert_awaited_once_with("2026-10")
