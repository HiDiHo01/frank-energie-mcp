"""Tests for the tools package."""

from __future__ import annotations

from frank_energie_mcp.tools import __doc__ as tools_doc


def test_tools_package_docstring_exists() -> None:
    """The tools package should expose a module docstring."""
    assert tools_doc is not None
    assert "Tool implementations" in tools_doc
