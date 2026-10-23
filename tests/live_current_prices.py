"""Live, unauthenticated Frank Energie price smoke test for GitHub Actions."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from math import isfinite
from urllib.error import URLError

from frank_energie_mcp.library import FrankEnergieLibraryBridge, FrankEnergieService


async def run() -> None:
    """Request public prices without credentials and validate the current interval."""
    for key in ("FRANK_ENERGIE_USERNAME", "FRANK_ENERGIE_PASSWORD", "FRANK_ENERGIE_SITE_REFERENCE"):
        if os.environ.get(key):
            raise RuntimeError("Live test requires an environment without account credentials.")

    # Use the same factory as production, but explicitly disable all authentication.
    from python_frank_energie.frank_energie import FrankEnergie

    service = FrankEnergieService(FrankEnergieLibraryBridge(factory=FrankEnergie))
    result = await asyncio.wait_for(service.get_current_prices(), timeout=40)
    electricity = result.get("electricity")
    if not isinstance(electricity, dict):
        raise ValueError("No current electricity price returned.")
    price = electricity.get("total")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not isfinite(price):
        raise ValueError("Current electricity price is missing or not finite.")
    start = datetime.fromisoformat(electricity["date_from"])
    end = datetime.fromisoformat(electricity["date_till"])
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("Electricity timestamps are not timezone-aware or ordered.")
    now = datetime.now(start.tzinfo)
    if not start <= now < end:
        raise ValueError("Electricity price interval does not cover current time.")
    if electricity.get("unit") != "kWh":
        raise ValueError("Electricity price unit is not kWh.")
    print("PASS: anonymous electricity price and timezone-aware interval validated.")
    print(f"Price: {price} EUR/kWh; interval: {start.isoformat()} - {end.isoformat()}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (TimeoutError, ConnectionError, OSError, URLError) as exc:
        print(f"NETWORK_ERROR: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"API_RESPONSE_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(3)
    except Exception as exc:
        print(f"API_OR_LIBRARY_ERROR: {type(exc).__name__}", file=sys.stderr)
        sys.exit(4)
