"""Live anonymous connectivity check through the official Frank Energie client.

Exit codes: 0 connected, 2 network/timeout, 3 API or response failure,
4 unexpected client failure. No account credentials or raw responses are logged.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from aiohttp import ClientError
from python_frank_energie import FrankEnergie


async def run() -> None:
    """Verify the public MarketPrices API can be reached and parsed."""
    for name in ("FRANK_ENERGIE_USERNAME", "FRANK_ENERGIE_PASSWORD", "FRANK_ENERGIE_SITE_REFERENCE"):
        if os.environ.get(name):
            raise RuntimeError("Connectivity test must run without account credentials.")

    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    async with FrankEnergie() as client:
        result = await asyncio.wait_for(client.prices(today), timeout=30)

    if result is None or getattr(result, "electricity", None) is None:
        raise ValueError("MarketPrices returned no electricity series.")
    print("PASS: public Frank Energie MarketPrices API is reachable and parsed successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (TimeoutError, OSError, ClientError) as exc:
        print(f"NETWORK_ERROR: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
    except ValueError:
        print("API_RESPONSE_ERROR: Missing electricity price series.", file=sys.stderr)
        sys.exit(3)
    except Exception as exc:
        print(f"API_OR_CLIENT_ERROR: {type(exc).__name__}", file=sys.stderr)
        sys.exit(4)
