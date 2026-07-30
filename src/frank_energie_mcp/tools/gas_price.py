"""Gas price tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class GasPriceResult:
    """Represent the gas price tool payload."""

    message: str



def get_gas_price() -> ToolResponse:
    """Return the gas price payload.

    This is a scaffold for the MCP tool implementation.
    """
    result = GasPriceResult(message="Not implemented yet.")
    return ToolResponse(status="ok", data=result)
