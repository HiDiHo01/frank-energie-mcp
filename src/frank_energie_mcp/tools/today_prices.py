"""Today prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class TodayPricesResult:
    """Represent the today prices tool payload."""

    message: str



def get_today_prices() -> ToolResponse:
    """Return today's prices payload.

    This is a scaffold for the MCP tool implementation.
    """
    result = TodayPricesResult(message="Not implemented yet.")
    return ToolResponse(status="ok", data=result)
