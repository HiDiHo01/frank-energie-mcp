"""Authentication helpers for frank-energie-mcp."""

from __future__ import annotations


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class AuthenticationManager:
    """Manage authentication for the MCP server.

    This is a placeholder for the integration with `python-frank-energie`.
    """

    def __init__(self) -> None:
        """Initialize the authentication manager."""

    def ensure_authenticated(self) -> None:
        """Ensure the current session is authenticated.

        Raises:
            AuthenticationError: If authentication is missing or invalid.
        """
        raise AuthenticationError("Authentication is not implemented yet.")
