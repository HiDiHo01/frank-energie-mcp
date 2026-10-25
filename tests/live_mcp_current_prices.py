"""Live anonymous MCP tool smoke test for the current electricity tariff."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from math import isfinite

from mcp.types import TextContent

from frank_energie_mcp.server import create_server


async def run() -> None:
    """Call the real MCP tool handler and validate its public price response."""
    for key in ("FRANK_ENERGIE_USERNAME", "FRANK_ENERGIE_PASSWORD", "FRANK_ENERGIE_SITE_REFERENCE"):
        if os.environ.get(key):
            raise RuntimeError("Live test requires an environment without account credentials.")

    server = create_server()
    response = await asyncio.wait_for(
        server.call_tool("get_current_prices", {"resolution": "PT15M"}), timeout=40
    )
    content = response[0] if isinstance(response, tuple) else response
    if not isinstance(content, list) or not content or not isinstance(content[0], TextContent):
        raise ValueError("Unexpected MCP tool response shape.")
    data = json.loads(content[0].text)
    if not isinstance(data, dict):
        raise ValueError("Unexpected MCP price payload.")
    electricity = data.get("electricity")
    if not isinstance(electricity, dict):
        raise ValueError("Current electricity interval is missing.")
    price = electricity.get("total")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not isfinite(price):
        raise ValueError("Current electricity price is not finite.")
    start = datetime.fromisoformat(electricity["date_from"])
    end = datetime.fromisoformat(electricity["date_till"])
    if start.tzinfo is None or end.tzinfo is None or not start <= datetime.now(start.tzinfo) < end:
        raise ValueError("Current electricity interval is invalid.")
    if str(electricity.get("unit", "")).casefold() != "kwh":
        raise ValueError("Electricity unit is not kWh.")
    print("PASS: live MCP get_current_prices returned a valid current tariff.")
    print(f"Price: {price} EUR/kWh; interval: {start.isoformat()} - {end.isoformat()}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as exc:
        print(f"LIVE_MCP_TEST_FAILED: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
