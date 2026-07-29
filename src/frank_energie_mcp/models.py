"""Data models for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PriceRecord:
    """Represent a single price entry."""

    timestamp: str
    price: float


@dataclass(slots=True, frozen=True)
class ToolResponse:
    """Represent a generic MCP tool response."""

    status: str
    data: object
