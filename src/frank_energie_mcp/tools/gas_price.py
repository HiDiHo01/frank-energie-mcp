"""Gas price tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class GasPriceResult:
    """Represent the gas price tool payload."""

    message: str
    source: str = "python-frank-energie"



def _extract_gas_price_payload(data: Any) -> GasPriceResult:
    """Convert library data into the MCP response model.

    This helper keeps the MCP boundary narrow and provides a single place for
    adapting the eventual `python-frank-energie` response shape.
    """
    if isinstance(data, GasPriceResult):
        return data

    return GasPriceResult(message="Not implemented yet.")



def get_gas_price() -> ToolResponse:
    """Return the gas price payload.

    The actual `python-frank-energie` integration will be wired in next.
    """
    result = _extract_gas_price_payload(None)
    return ToolResponse(status="ok", data=result)
