"""Tomorrow prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ..library import default_library_bridge
from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class TomorrowPricesResult:
    """Represent the tomorrow prices tool payload."""

    message: str
    source: str = "python-frank-energie"



def _extract_tomorrow_prices_payload(data: Any) -> TomorrowPricesResult:
    """Convert library data into the MCP response model.

    This helper keeps the MCP boundary narrow and provides a single place for
    adapting the eventual `python-frank-energie` response shape.
    """
    if isinstance(data, TomorrowPricesResult):
        return data

    return TomorrowPricesResult(message="Not implemented yet.")


async def get_tomorrow_prices() -> ToolResponse:
    """Return tomorrow's prices payload from the Frank Energie library."""
    bridge = default_library_bridge()
    tomorrow = date.today() + timedelta(days=1)
    async with bridge.session() as client:
        data = await client.prices(tomorrow, tomorrow)

    result = _extract_tomorrow_prices_payload(data)
    return ToolResponse(status="ok", data=result)
