"""Current prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class CurrentPricesResult:
    """Represent the current prices tool payload."""

    message: str



def get_current_prices() -> ToolResponse:
    """Return the current price payload.

    This is still a scaffold, but the return shape is now explicit and
    testable while the real `python-frank-energie` integration is added.
    """
    result = CurrentPricesResult(message="Not implemented yet.")
    return ToolResponse(status="ok", data=result)
