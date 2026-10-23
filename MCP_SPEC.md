# MCP Specification

## Implementation status

The server uses the official Python MCP SDK's FastMCP runtime. Nine read-only asynchronous tools, one static resource, and one static prompt are registered. The interface remains under development and is not yet production-ready.

## Transports

`python -m frank_energie_mcp` starts stdio by default. Set `FRANK_ENERGIE_MCP_TRANSPORT=streamable-http` to start Streamable HTTP at `http://127.0.0.1:8000/mcp` by default. The HTTP host must be `127.0.0.1`; `FRANK_ENERGIE_MCP_PORT` must be an integer from 1 to 65535. Unsupported transports are rejected.

The HTTP listener has no application-level inbound authentication. Do not expose it publicly, through port forwarding, or through an unauthenticated proxy or tunnel. The effective SDK origin/DNS-rebinding protections have not been independently verified.

## Tools

All price tools accept an optional `resolution` parameter: `PT15M` (default) or `PT60M`. Other values are rejected by the MCP tool schema.

| Tool | Service operation | Current response |
| --- | --- | --- |
| `get_current_prices` | `get_current_prices(resolution)` | Object with `electricity` and `gas` active upstream `current_hour` intervals, each a normalized record or `null` |
| `get_today_prices` | `get_today_prices(resolution)` | Normalized `electricity` and `gas` interval arrays from `prices(today, resolution=...)` |
| `get_tomorrow_prices` | `get_tomorrow_prices(resolution)` | Normalized interval arrays from `prices(tomorrow, resolution=...)` |
| `get_average_prices` | `get_average_prices(day, resolution)` | Per-energy average of all available normalized `total` values, interval count, first/last timestamps, observed and expected coverage seconds, and `empty`/`incomplete`/`complete` status. `day` defaults to today in Europe/Amsterdam. Overlaps and out-of-day intervals are rejected. |
| `get_lowest_price` | `get_lowest_price(day, resolution)` | Minimum total interval for each energy type, with coverage metadata. |
| `get_highest_price` | `get_highest_price(day, resolution)` | Maximum total interval for each energy type, with coverage metadata. |
| `get_gas_price` | `get_gas_price(resolution)` | Normalized active gas interval or `null` |
| `get_account` | `get_account()` | After a successful authenticated account request, returns only `{"authenticated": true}`; account details are deliberately not exposed |
| `list_sites` | `list_sites()` | `{"count": N}` for a recognized site collection; site identifiers and addresses are not exposed |

Today and tomorrow use calendar dates in `Europe/Amsterdam`. The active interval is selected by the upstream `current_hour` property; the MCP layer does not recalculate the price or infer missing intervals.

## Price response contract

`price_schemas.py` defines strict Pydantic `PriceInterval` and `MarketPriceResponse` models. Each returned interval contains only:

- `date_from`, `date_till`: timezone-aware ISO 8601 timestamps
- `total`: finite numeric total converted to a float
- `unit`: optional upstream `per_unit` (preferred) or `unit`
- `energy_type`: optional upstream energy type

Intervals must have valid, ordered, timezone-aware timestamps and a finite numeric total. Full-day arrays must be lists with at most 200 entries **per energy type**; other shapes or oversized arrays raise an error. The implementation validates the serialized arrays in Pydantic JSON mode. Unknown upstream fields, including credentials, are excluded by explicit field selection.

There is no `status/source/data` response envelope. The account and site responses use separate minimal schemas in `server.py`. The 200-entry limit is a **defensive MCP response-size bound**, not an upstream API contract. Upstream `PriceResolution` supports `PT15M` and `PT60M`; for complete Europe/Amsterdam calendar days these imply 92/96/100 or 23/24/25 intervals respectively (spring DST/normal/autumn DST). Actual API responses may be incomplete, so these counts are not enforced. The 200-entry cap intentionally leaves headroom beyond a full day while rejecting unexpectedly large series.

## Authentication and upstream access

`FrankEnergieLibraryBridge` creates an upstream `python-frank-energie` client per request, optionally logs in, and closes the client in a `finally` block.

- Public market prices can be requested without credentials.
- `FRANK_ENERGIE_USERNAME` and `FRANK_ENERGIE_PASSWORD` must be configured together for account/site operations.
- `get_account` also requires `FRANK_ENERGIE_SITE_REFERENCE`.
- `get_account` invokes upstream `user(site_reference)`; `list_sites` invokes `UserSites()`.
- The MCP layer does not implement GraphQL, token persistence, token renewal, or price calculations.

## Errors and privacy

Tool handlers wrap service failures in a generic `ToolError("Frank Energie request failed.")` and log only the exception class, not its message. The site response rejects unrecognized structures. The tool boundary intentionally avoids returning raw account and site objects. These controls have unit-test coverage but are not a complete security or production-readiness assessment.

## Resource and prompt

- `frank-energie://capabilities`: static read-only description of available price tools and authentication requirement.
- `summarize_energy_prices`: static instructions to compare today and tomorrow while preserving units and timestamps and avoiding fabricated data.

No dynamic resources or additional prompts are registered.

## Validation

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest -q
```

The test suite covers service delegation, upstream call signatures, session cleanup, selected normalization/privacy boundaries, MCP tool registration, and transport configuration. Synthetic regression tests cover 23-, 24-, and 25-hour Amsterdam days at both supported resolutions. Real-client interoperability, upstream production behavior, authentication lifecycle, and HTTP ingress security still require validation. Passing CI is required before merging; this document does not assert that the current commit passes.

## Next steps

1. Validate live upstream interval behavior; the 200-entry MCP limit is intentionally independent of the upstream contract.
2. Validate end-to-end MCP calls over stdio and loopback Streamable HTTP.
3. Review authentication lifecycle, client authorization for any external deployment, and error handling.
4. Align tool names and account/site output contracts with intended client functionality.
