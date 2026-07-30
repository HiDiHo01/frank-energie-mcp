"""List sites tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class SiteResult:
    """Represent a single site entry."""

    name: str


@dataclass(slots=True, frozen=True)
class ListSitesResult:
    """Represent the list sites tool payload."""

    sites: tuple[SiteResult, ...]



def list_sites() -> ToolResponse:
    """Return the configured site list.

    This is a scaffold for the MCP tool implementation.
    """
    result = ListSitesResult(sites=())
    return ToolResponse(status="ok", data=result)
