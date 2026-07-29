"""Configuration helpers for frank-energie-mcp."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Config:
    """Runtime configuration for the MCP server."""

    server_name: str = "frank-energie-mcp"
