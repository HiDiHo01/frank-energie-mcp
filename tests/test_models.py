"""Tests for the MCP data models."""

from __future__ import annotations

from frank_energie_mcp.models import PriceRecord, ToolResponse


def test_price_record_fields() -> None:
    """PriceRecord should store the expected fields."""
    record = PriceRecord(timestamp="2026-07-29T00:00:00+02:00", price=0.25)
    assert record.timestamp == "2026-07-29T00:00:00+02:00"
    assert record.price == 0.25


def test_tool_response_fields() -> None:
    """ToolResponse should store status and data."""
    response = ToolResponse(status="ok", data={"value": 1})
    assert response.status == "ok"
    assert response.data == {"value": 1}
