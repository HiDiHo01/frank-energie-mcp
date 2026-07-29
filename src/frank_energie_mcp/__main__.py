"""Command-line entrypoint for frank-energie-mcp."""

from __future__ import annotations

from .server import main


if __name__ == "__main__":
    raise SystemExit(main())
