"""List sites tool for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..library import default_library_bridge
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


async def list_sites() -> ToolResponse:
    """Return the configured site list from the Frank Energie library."""
    bridge = default_library_bridge()
    async with bridge.session() as client:
        data = await client.user()

    result = _extract_sites_payload(data)
    return ToolResponse(status="ok", data=result)
