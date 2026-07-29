"""Current prices tool for frank-energie-mcp."""

from __future__ import annotations

from typing import Any

from ..models import ToolResponse


def get_current_prices() -> ToolResponse:
    """Return the current price payload.

    This is a scaffold for the MCP tool implementation.
    """
    return ToolResponse(status="ok", data={"message": "Not implemented yet."})
