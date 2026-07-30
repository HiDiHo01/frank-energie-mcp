"""MCP server bootstrap for Frank Energie."""

from __future__ import annotations

from typing import Final

DEFAULT_SERVER_NAME: Final[str] = "frank-energie-mcp"


class Server:
    """Represent the MCP server bootstrap.

    The class is intentionally minimal until the real MCP runtime wiring is
    added.
    """

    def __init__(self, server_name: str = DEFAULT_SERVER_NAME) -> None:
        """Initialize the server bootstrap."""
        self.server_name = server_name

    def run(self) -> int:
        """Run the MCP server entrypoint.

        Returns:
            An integer process exit code.
        """
        print(f"Starting {self.server_name}")
        return 0



def main() -> int:
    """Run the MCP server entrypoint.

    Returns:
        An integer process exit code.
    """
    return Server().run()
