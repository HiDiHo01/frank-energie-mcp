"""Privacy-safe invoice aggregation and PV summary tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def service(client: AsyncMock, *, site: str | None = "site") -> FrankEnergieService:
    """Create a credentialed mock-backed service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


@pytest.mark.asyncio
async def test_invoice_aggregation_filters_year_and_private_fields() -> None:
    """Aggregate only totals, never identifiers or invoice descriptions."""
    client = AsyncMock()
    client.invoices.return_value = SimpleNamespace(
        all_periods_invoices=[
            SimpleNamespace(
                id="private-1",
                StartDate=datetime(2026, 1, 1, tzinfo=UTC),
                TotalAmount=12.0,
            ),
            SimpleNamespace(
                id="private-2",
                StartDate=datetime(2026, 7, 1, tzinfo=UTC),
                TotalAmount=18.0,
            ),
            SimpleNamespace(
                id="private-3",
                StartDate=datetime(2025, 7, 1, tzinfo=UTC),
                TotalAmount=50.0,
            ),
        ]
    )
    result = await service(client).get_invoice_statistics(2026)
    assert result == {
        "year": 2026,
        "invoice_count": 2,
        "total_amount": 30.0,
        "average_amount": 15.0,
    }
    client.invoices.assert_awaited_once_with("site")
    assert "private" not in str(result)


@pytest.mark.asyncio
async def test_invoice_validation() -> None:
    """Reject missing site, invalid year and nonfinite amounts."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await service(client, site=None).get_invoice_statistics(2026)
    with pytest.raises(ValueError, match="year"):
        await service(client).get_invoice_statistics(1999)
    client.invoices.return_value = SimpleNamespace(
        all_periods_invoices=[
            SimpleNamespace(
                StartDate=datetime(2026, 1, 1, tzinfo=UTC),
                TotalAmount=float("nan"),
            )
        ]
    )
    with pytest.raises(ValueError, match="finite"):
        await service(client).get_invoice_statistics(2026)


@pytest.mark.asyncio
async def test_pv_summary_allowlist() -> None:
    """Exclude device IDs and retain only status and numeric totals."""
    client = AsyncMock()
    client.smart_pv_system_summary.return_value = SimpleNamespace(
        device_id="private-device",
        operational_status="ACTIVE",
        steering_status="ON",
        total_bonus=1.5,
        total_result=3.0,
    )
    result = await service(client).get_smart_pv_system_summary("device")
    assert result == {
        "available": True,
        "operational_status": "ACTIVE",
        "steering_status": "ON",
        "total_bonus": 1.5,
        "total_result": 3.0,
    }
    client.smart_pv_system_summary.assert_awaited_once_with("device")
    assert "private" not in str(result)


@pytest.mark.asyncio
async def test_new_mcp_tools_delegate() -> None:
    """Verify both new FastMCP registrations."""
    mock = AsyncMock()
    server = create_server(mock)
    await server.call_tool("get_invoice_statistics", {"year": 2026})
    await server.call_tool("get_smart_pv_system_summary", {"device_id": "device"})
    mock.get_invoice_statistics.assert_awaited_once_with(2026)
    mock.get_smart_pv_system_summary.assert_awaited_once_with("device")
