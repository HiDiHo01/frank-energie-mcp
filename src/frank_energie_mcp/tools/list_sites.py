"""List sites tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ToolResponse


@dataclass(slots=True, frozen=True)
class SiteResult:
    """Represent a single site entry."""

    name: str
    source: str = "python-frank-energie"


@dataclass(slots=True, frozen=True)
class ListSitesResult:
    """Represent the list sites tool payload."""

    sites: tuple[SiteResult, ...]



def _extract_sites_payload(data: Any) -> ListSitesResult:
    """Convert library data into the MCP response model.

    This helper keeps the MCP boundary narrow and provides a single place for
    adapting the eventual `python-frank-energie` response shape.
    """
    if isinstance(data, ListSitesResult):
        return data

    return ListSitesResult(sites=())



def list_sites() -> ToolResponse:
    """Return the configured site list.

    The actual `python-frank-energie` integration will be wired in next.
    """
    result = _extract_sites_payload(None)
    return ToolResponse(status="ok", data=result)
