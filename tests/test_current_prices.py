"""Tests for the current prices tool scaffold."""

from __future__ import annotations

from frank_energie_mcp.tools.current_prices import CurrentPricesResult, get_current_prices


def test_get_current_prices_returns_tool_response() -> None:
    """The tool should return a ToolResponse instance."""
    response = get_current_prices()

    assert response.status == "ok"
    assert isinstance(response.data, CurrentPricesResult)
    assert response.data.message == "Not implemented yet."
