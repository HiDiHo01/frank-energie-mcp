"""Today prices tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..library import default_library_bridge
from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class TodayPricesResult:
    """Represent the today prices tool payload."""

    message: str
    source: str = "python-frank-energie"



def _extract_today_prices_payload(data: Any) -> TodayPricesResult:
    """Convert library data into the MCP response model.

    This helper keeps the MCP boundary narrow and provides a single place for
    adapting the eventual `python-frank-energie` response shape.
    """
    if isinstance(data, TodayPricesResult):
        return data

    return TodayPricesResult(message="Not implemented yet.")


async def get_today_prices() -> ToolResponse:
    """Return today's prices payload from the Frank Energie library."""
    bridge = default_library_bridge()
    async with bridge.session() as client:
        data = await client.prices(date.today(), date.today())

    result = _extract_today_prices_payload(data)
    return ToolResponse(status="ok", data=result)
