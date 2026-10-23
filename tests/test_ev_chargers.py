"""Tests for read-only EV charger statistics."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def make_service(client: AsyncMock, site: str | None = "test-site") -> FrankEnergieService:
    """Create an authenticated mock-backed service."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
            site_reference=site,
        )
    )


@pytest.mark.asyncio
async def test_charger_statistics_count_without_identifiers() -> None:
    """Count capability flags without exposing charger IDs or interventions."""
    client = AsyncMock()
    client.enode_chargers.return_value = SimpleNamespace(
        chargers=[
            SimpleNamespace(
                id="private-1",
                is_reachable=True,
                can_smart_charge=True,
                charge_settings=SimpleNamespace(is_smart_charging_enabled=True),
            ),
            SimpleNamespace(
                id="private-2",
                is_reachable=False,
                can_smart_charge=True,
                charge_settings=SimpleNamespace(is_smart_charging_enabled=False),
            ),
        ]
    )
    result = await make_service(client).get_ev_charger_statistics(date(2026, 10, 1))
    assert result == {
        "charger_count": 2,
        "reachable_count": 1,
        "smart_capable_count": 2,
        "smart_enabled_count": 1,
    }
    assert "private" not in str(result)
    client.enode_chargers.assert_awaited_once_with("test-site", date(2026, 10, 1))


@pytest.mark.asyncio
async def test_charger_statistics_empty_and_malformed() -> None:
    """Handle empty charger collections and reject malformed flags."""
    client = AsyncMock()
    client.enode_chargers.return_value = SimpleNamespace(chargers=[])
    assert (await make_service(client).get_ev_charger_statistics(date(2026, 10, 1)))[
        "charger_count"
    ] == 0
    client.enode_chargers.return_value = SimpleNamespace(
        chargers=[
            SimpleNamespace(
                is_reachable="yes",
                can_smart_charge=True,
                charge_settings=SimpleNamespace(is_smart_charging_enabled=True),
            )
        ]
    )
    with pytest.raises(ValueError, match="capability flags"):
        await make_service(client).get_ev_charger_statistics(date(2026, 10, 1))


@pytest.mark.asyncio
async def test_charger_statistics_requires_site() -> None:
    """Reject missing site references without upstream calls."""
    client = AsyncMock()
    with pytest.raises(RuntimeError, match="SITE_REFERENCE"):
        await make_service(client, site=None).get_ev_charger_statistics(
            date(2026, 10, 1)
        )
    client.enode_chargers.assert_not_awaited()


@pytest.mark.asyncio
async def test_charger_tool_registration() -> None:
    """Verify the MCP wrapper forwards the selected date."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool("get_ev_charger_statistics", {"start_date": "2026-10-01"})
    service.get_ev_charger_statistics.assert_awaited_once_with(date(2026, 10, 1))
