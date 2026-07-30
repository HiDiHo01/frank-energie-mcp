"""Current prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..library import default_library_bridge
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


async def get_current_prices() -> ToolResponse:
    """Return the current price payload from the Frank Energie library."""
    bridge = default_library_bridge()
    async with bridge.session() as client:
        data = await client.prices(date.today(), date.today())

    result = _extract_current_prices_payload(data)
    return ToolResponse(status="ok", data=result)
