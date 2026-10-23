# MCP Specification

## Implementation status

The official Python MCP SDK provides the FastMCP stdio runtime. This document distinguishes registered interfaces from fully operational features. The interface is not yet stable.

## Tools

Six asynchronous, argument-free tools are registered:

| Tool | Service operation | Status |
| --- | --- | --- |
| `get_current_prices` | `get_current_prices()` | Returns today's market prices; current interval not isolated |
| `get_today_prices` | `get_today_prices()` | Calls upstream `prices(today)` |
| `get_tomorrow_prices` | `get_tomorrow_prices()` | Calls upstream `prices(tomorrow)` |
| `get_gas_price` | `get_gas_price()` | Returns today's market prices; gas not isolated |
| `get_account` | `get_account()` | Raises until authentication and site selection are implemented |
| `list_sites` | `list_sites()` | Calls upstream `UserSites()`; requires authentication |

Dates use the `Europe/Amsterdam` calendar. No tool should fabricate missing price data.

## Resources and prompts

- `frank-energie://capabilities`: registered static, read-only text resource describing capabilities.
- `summarize_energy_prices`: registered static prompt instructing the client to compare today and tomorrow, preserving units and timestamps.

Dynamic price/account resources and further prompts remain future work.

## Upstream contracts

All data access is delegated to `python-frank-energie`. Verified upstream method signatures include `prices(start_date: date | None = None, resolution=...)`, `UserSites(site_reference: str | None = None)` and `user(site_reference: str | None = None)`. Account and site operations require authentication; `user()` additionally needs a valid site reference.

The bridge creates and closes its asynchronous client per request. Do not reimplement GraphQL, price calculations or token renewal in the MCP layer.

## Output and error behavior

The tool handlers currently forward service results. A stable JSON envelope and upstream model serialization have **not** been implemented or validated. The earlier proposed `status/source/data` envelope is a design goal, not current behavior.

Authentication, transport failures, sensitive-data redaction and MCP-compatible error translation require further implementation and tests.

## Testing

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest -q
```

Regression tests cover selected upstream method signatures, session cleanup, tool registration and resource/prompt discovery. A real MCP client interoperability test is still required.

## Planned improvements

1. Secure authentication and site-reference selection through the upstream library.
2. Accurate current-interval and gas-only extraction using verified upstream models.
3. Deterministic, serializable, privacy-aware MCP response schemas.
4. End-to-end protocol and failure-path tests.
