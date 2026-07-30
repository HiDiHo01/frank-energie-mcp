"""Current prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class CurrentPricesResult:
    """Represent the current prices tool payload."""

    message: str
    source: str = "python-frank-energie"



def _extract_current_prices_payload(data: Any) -> CurrentPricesResult:
    """Convert library data into the MCP response model.

    This helper keeps the MCP boundary narrow and provides a single place for
    adapting the eventual `python-frank-energie` response shape.
    """
    if isinstance(data, CurrentPricesResult):
        return data

    return CurrentPricesResult(message="Not implemented yet.")



def get_current_prices() -> ToolResponse:
    """Return the current price payload.

    The actual `python-frank-energie` integration will be wired in next.
    """
    result = _extract_current_prices_payload(None)
    return ToolResponse(status="ok", data=result)
