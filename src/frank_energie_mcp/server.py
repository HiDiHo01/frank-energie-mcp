"""MCP server bootstrap for Frank Energie."""

from __future__ import annotations

from typing import Final

DEFAULT_SERVER_NAME: Final[str] = "frank-energie-mcp"


def main() -> int:
    """Run the MCP server entrypoint.

    Returns:
        An integer process exit code.
    """
    print(f"Starting {DEFAULT_SERVER_NAME}")
    return 0
