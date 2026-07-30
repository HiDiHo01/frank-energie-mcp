"""Tests for the MCP server scaffold."""

from __future__ import annotations

from frank_energie_mcp.server import DEFAULT_SERVER_NAME, main


def test_main_returns_success_exit_code() -> None:
    """The server entrypoint should return a successful exit code."""
    assert main() == 0


def test_default_server_name() -> None:
    """The default server name should remain stable."""
    assert DEFAULT_SERVER_NAME == "frank-energie-mcp"
