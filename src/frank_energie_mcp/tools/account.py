"""Account tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class AccountResult:
    """Represent the account tool payload."""

    message: str
    source: str = "python-frank-energie"



def _extract_account_payload(data: Any) -> AccountResult:
    """Convert library data into the MCP response model.

    This helper keeps the MCP boundary narrow and provides a single place for
    adapting the eventual `python-frank-energie` response shape.
    """
    if isinstance(data, AccountResult):
        return data

    return AccountResult(message="Not implemented yet.")



def get_account() -> ToolResponse:
    """Return the account payload.

    The actual `python-frank-energie` integration will be wired in next.
    """
    result = _extract_account_payload(None)
    return ToolResponse(status="ok", data=result)
