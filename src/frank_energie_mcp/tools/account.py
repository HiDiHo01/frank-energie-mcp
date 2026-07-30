"""Account tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class AccountResult:
    """Represent the account tool payload."""

    message: str



def get_account() -> ToolResponse:
    """Return the account payload.

    This is a scaffold for the MCP tool implementation.
    """
    result = AccountResult(message="Not implemented yet.")
    return ToolResponse(status="ok", data=result)
