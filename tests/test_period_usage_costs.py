"""Billing-period usage and costs allowlist tests."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, *, site: str | None = "site") -> FrankEnergieService:
    """Create an authenticated service backed by an isolated upstream mock."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


@pytest.mark.asyncio
async def test_period_usage_costs_allowlist() -> None:
    """Expose only category totals, not billing identifiers or detailed items."""
    client = AsyncMock()
    client.period_usage_and_costs.return_value = SimpleNamespace(
        _id="private-period-id",
        electricity=SimpleNamespace(
            unit="kWh", usage_total=100.0, costs_total=20.0, items=["private"]
        ),
        gas=SimpleNamespace(unit="m3", usage_total=30.0, costs_total=35.0),
        feed_in=None,
    )
    result = await make_service(client).get_period_usage_and_costs(date(2026, 10, 1))
    assert result == {
        "available": True,
        "start_date": "2026-10-01",
        "categories": {
            "electricity": {"unit": "kWh", "usage_total": 100.0, "costs_total": 20.0},
            "gas": {"unit": "m3", "usage_total": 30.0, "costs_total": 35.0},
            "feed_in": None,
        },
    }
    assert "private" not in str(result)
    client.period_usage_and_costs.assert_awaited_once_with("site", "2026-10-01")


@pytest.mark.asyncio
async def test_period_usage_costs_absent_and_invalid() -> None:
    """Handle absent periods and reject nonfinite totals."""
    client = AsyncMock()
    client.period_usage_and_costs.return_value = None
    assert await make_service(client).get_period_usage_and_costs(date(2026, 10, 1)) == {
        "available": False,
        "start_date": "2026-10-01",
    }
    client.period_usage_and_costs.return_value = SimpleNamespace(
        electricity=SimpleNamespace(
            unit="kWh", usage_total=2.0, costs_total=float("inf")
        ),
        gas=None,
        feed_in=None,
    )
    with pytest.raises(ValueError, match="usage or cost"):
        await make_service(client).get_period_usage_and_costs(date(2026, 10, 1))


@pytest.mark.asyncio
async def test_period_usage_costs_require_site() -> None:
    """Reject calls without a configured delivery-site reference."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await make_service(client, site=None).get_period_usage_and_costs(
            date(2026, 10, 1)
        )
    client.period_usage_and_costs.assert_not_awaited()


@pytest.mark.asyncio
async def test_period_usage_costs_mcp_registration() -> None:
    """FastMCP forwards parsed dates to the service."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_period_usage_and_costs", {"start_date": "2026-10-01"})
    service.get_period_usage_and_costs.assert_awaited_once_with(date(2026, 10, 1))
