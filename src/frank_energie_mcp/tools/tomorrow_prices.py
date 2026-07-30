"""Tomorrow prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class TomorrowPricesResult:
    """Represent the tomorrow prices tool payload."""

    message: str



def get_tomorrow_prices() -> ToolResponse:
    """Return tomorrow's prices payload.

    This is a scaffold for the MCP tool implementation.
    """
    result = TomorrowPricesResult(message="Not implemented yet.")
    return ToolResponse(status="ok", data=result)
