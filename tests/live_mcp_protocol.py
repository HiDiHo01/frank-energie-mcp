"""Live MCP protocol smoke test over a local stdio client session."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from math import isfinite

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent


async def run() -> None:
    """Initialize a real MCP client, discover tools and read the current tariff."""
    env = os.environ.copy()
    for key in (
        "FRANK_ENERGIE_USERNAME",
        "FRANK_ENERGIE_PASSWORD",
        "FRANK_ENERGIE_SITE_REFERENCE",
    ):
        env.pop(key, None)
    env["FRANK_ENERGIE_MCP_TRANSPORT"] = "stdio"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "frank_energie_mcp"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=20)
            listed = await asyncio.wait_for(session.list_tools(), timeout=20)
            if "get_current_prices" not in {tool.name for tool in listed.tools}:
                raise ValueError("Expected current-price MCP tool is missing.")
            result = await asyncio.wait_for(
                session.call_tool("get_current_prices", {"resolution": "PT15M"}),
                timeout=50,
            )
    if result.isError:
        raise ValueError("MCP current-price tool returned an error.")
    if not result.content or not isinstance(result.content[0], TextContent):
        raise ValueError("MCP current-price response is not text.")
    payload = json.loads(result.content[0].text)
    if not isinstance(payload, dict):
        raise ValueError("MCP current-price payload is not an object.")
    electricity = payload.get("electricity")
    if not isinstance(electricity, dict):
        raise ValueError("MCP electricity price is missing.")
    price = electricity.get("total")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not isfinite(price):
        raise ValueError("MCP electricity price is not finite.")
    if str(electricity.get("unit", "")).casefold() != "kwh":
        raise ValueError("MCP electricity unit is not kWh.")
    start = datetime.fromisoformat(electricity["date_from"])
    end = datetime.fromisoformat(electricity["date_till"])
    if start.tzinfo is None or end.tzinfo is None or not start <= datetime.now(start.tzinfo) < end:
        raise ValueError("MCP electricity interval does not cover current time.")
    print("PASS: MCP initialize, tools/list and tools/call succeeded over stdio.")
    print(f"Price: {price} EUR/kWh; interval: {start.isoformat()} - {end.isoformat()}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as exc:
        print(f"LIVE_MCP_PROTOCOL_FAILED: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
