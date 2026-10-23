"""Battery trading-session aggregation and privacy regression tests."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService
from frank_energie_mcp.server import create_server


def service_for(client: AsyncMock) -> FrankEnergieService:
    """Create an authenticated service backed by an isolated fake client."""
    return FrankEnergieService(
        FrankEnergieLibraryBridge(
            factory=lambda: client,
            username="fake@example.invalid",
            password="placeholder",
        )
    )


@pytest.mark.asyncio
async def test_battery_sessions_aggregate_and_hide_device_metadata() -> None:
    """Only aggregate non-null session results; omit IDs and raw sessions."""
    client = AsyncMock()
    client.smart_battery_sessions.return_value = SimpleNamespace(
        device_id="private-device",
        sessions=[
            SimpleNamespace(result=3.5, trade_index=1),
            SimpleNamespace(result=-1.0, trade_index=2),
            SimpleNamespace(result=None, trade_index=3),
        ],
    )
    result = await service_for(client).get_smart_battery_session_statistics(
        "device", date(2026, 10, 1), date(2026, 10, 3)
    )
    assert result == {
        "available": True,
        "session_count": 3,
        "result_count": 2,
        "total_session_result": 2.5,
        "average_session_result": 1.25,
    }
    assert "private" not in str(result)
    client.smart_battery_sessions.assert_awaited_once_with(
        "device", date(2026, 10, 1), date(2026, 10, 3)
    )


@pytest.mark.asyncio
async def test_battery_sessions_missing_and_null_results() -> None:
    """Represent missing session data without fabricating a zero average."""
    client = AsyncMock()
    client.smart_battery_sessions.return_value = None
    result = await service_for(client).get_smart_battery_session_statistics(
        "device", date(2026, 10, 1), date(2026, 10, 3)
    )
    assert result["available"] is False
    assert result["average_session_result"] is None


@pytest.mark.asyncio
async def test_battery_sessions_validate_range_and_values() -> None:
    """Reject invalid dates and nonfinite session result values."""
    client = AsyncMock()
    service = service_for(client)
    with pytest.raises(ValueError, match="date range"):
        await service.get_smart_battery_session_statistics(
            "device", date(2026, 10, 3), date(2026, 10, 1)
        )
    client.smart_battery_sessions.return_value = SimpleNamespace(
        sessions=[SimpleNamespace(result=float("nan"))]
    )
    with pytest.raises(ValueError, match="session result"):
        await service.get_smart_battery_session_statistics(
            "device", date(2026, 10, 1), date(2026, 10, 3)
        )


@pytest.mark.asyncio
async def test_battery_session_tool_registration() -> None:
    """Verify FastMCP forwards device ID and parsed dates."""
    service = AsyncMock()
    server = create_server(service)
    await server.call_tool(
        "get_smart_battery_session_statistics",
        {
            "device_id": "device",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
        },
    )
    service.get_smart_battery_session_statistics.assert_awaited_once_with(
        "device", date(2026, 10, 1), date(2026, 10, 3)
    )
