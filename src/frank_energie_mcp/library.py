"""Bridge helpers for the `python_frank_energie` library."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol, cast


class _AsyncFrankEnergie(Protocol):
    """Protocol for the subset of the Frank Energie API used by the MCP layer."""

    async def login(self, username: str, password: str) -> Any:
        """Authenticate with Frank Energie."""

    async def user(self) -> Any:
        """Return the current user data."""

    async def invoices(self) -> Any:
        """Return invoice data."""

    async def month_summary(self) -> Any:
        """Return the month summary."""

    async def prices(self, start_date: date, end_date: date) -> Any:
        """Return prices for the requested date range."""

    async def user_prices(self, start_date: date, end_date: date | None = None) -> Any:
        """Return user-specific prices for the requested date range."""

    async def close(self) -> None:
        """Close the underlying HTTP session."""


@dataclass(slots=True, frozen=True)
class FrankEnergieLibraryBridge:
    """Encapsulate access to `python_frank_energie`.

    The bridge keeps the MCP layer isolated from the concrete library import so
    the rest of the repository can be tested against a narrow interface.
    """

    factory: Callable[[], _AsyncFrankEnergie]

    @asynccontextmanager
    async def session(self):
        """Create a managed Frank Energie client session."""
        client = self.factory()
        try:
            yield client
        finally:
            await client.close()


@dataclass(slots=True, frozen=True)
class FrankEnergieService:
    """High-level service helpers for MCP tool handlers."""

    bridge: FrankEnergieLibraryBridge

    async def get_current_prices(self) -> Any:
        """Return current prices for today."""
        async with self.bridge.session() as client:
            return await client.prices(date.today(), date.today())

    async def get_today_prices(self) -> Any:
        """Return today's prices."""
        async with self.bridge.session() as client:
            return await client.prices(date.today(), date.today())

    async def get_tomorrow_prices(self) -> Any:
        """Return tomorrow's prices."""
        tomorrow = date.today() + timedelta(days=1)
        async with self.bridge.session() as client:
            return await client.prices(tomorrow, tomorrow)

    async def get_gas_price(self) -> Any:
        """Return gas pricing data."""
        async with self.bridge.session() as client:
            return await client.prices(date.today(), date.today())

    async def get_account(self) -> Any:
        """Return the current account data."""
        async with self.bridge.session() as client:
            return await client.user()

    async def list_sites(self) -> Any:
        """Return the available sites."""
        async with self.bridge.session() as client:
            return await client.user()



def default_library_bridge() -> FrankEnergieLibraryBridge:
    """Return the default bridge for `python_frank_energie`.

    Importing the library happens lazily so the MCP package remains importable
    even if the dependency is missing during early scaffolding.
    """

    def _factory() -> _AsyncFrankEnergie:
        from python_frank_energie.frank_energie import FrankEnergie

        return cast(_AsyncFrankEnergie, FrankEnergie())

    return FrankEnergieLibraryBridge(factory=_factory)



def default_service() -> FrankEnergieService:
    """Return the default high-level service helper."""
    return FrankEnergieService(bridge=default_library_bridge())
