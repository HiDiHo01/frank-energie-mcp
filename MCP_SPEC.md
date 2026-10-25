# MCP Specification

## Implementation status

The server uses the official Python MCP SDK's FastMCP runtime. Fourteen read-only asynchronous tools, one static resource, and one static prompt are registered. The interface remains under development and is not yet production-ready.

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
| `get_lowest_period` | `get_lowest_period(period_minutes, day, resolution)` | Cheapest uninterrupted fixed-duration window for electricity and gas, selected by arithmetic mean of normalized `total`. |
| `get_price_threshold_periods` | `get_price_threshold_periods(threshold, comparison, day, resolution)` | Consecutive electricity and gas price intervals strictly below or above a finite threshold, with coverage metadata. |
| `calculate_energy_cost` | `calculate_energy_cost(start, end, consumption_kwh, resolution)` | Electricity cost estimate using duration-weighted normalized prices over a fully covered time range. |
| `get_best_start_time` | `get_best_start_time(period_minutes, day, resolution, consumption_kwh)` | Cheapest contiguous electricity window and optional estimated energy cost. |
| `get_highest_period` | `get_highest_period(period_minutes, day, resolution)` | Most expensive uninterrupted fixed-duration window, with the same response contract. |
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

## Daily statistics contracts

`get_average_prices`, `get_lowest_price` and `get_highest_price` accept
`day: date | None = None` and `resolution: "PT15M" | "PT60M" = "PT15M"`.
`day` is an ISO 8601 calendar date; omitted dates resolve to the current
`Europe/Amsterdam` date. Each operation requests upstream
`prices(day, resolution=resolution)` and uses `normalize_market_prices`
before aggregation or selection.

The outer response always has `date` (ISO date), `resolution`,
`electricity` and `gas` fields. The following is an illustrative shape,
not live API data:

```json
{
  "date": "2026-06-15",
  "resolution": "PT15M",
  "electricity": {
    "average_total": 0.25,
    "interval_count": 1,
    "first_interval": "2026-06-15T00:00:00+02:00",
    "last_interval": "2026-06-15T00:15:00+02:00",
    "coverage_seconds": 900,
    "expected_seconds": 86400,
    "complete": false,
    "status": "incomplete"
  },
  "gas": {
    "average_total": null,
    "interval_count": 0,
    "first_interval": null,
    "last_interval": null,
    "coverage_seconds": 0,
    "expected_seconds": 86400,
    "complete": false,
    "status": "empty"
  }
}
```

Average values are arithmetic means of available normalized `total` values
for each energy type; they are not duration-weighted. An empty series returns
`average_total: null`. No missing prices are synthesized.

The minimum and maximum tools replace the average-specific fields with
`price` (a complete normalized `PriceInterval`, or `null`), and include
`interval_count`, `coverage_seconds`, `expected_seconds`, and `status`.
They choose the minimum or maximum `total` value independently for electricity
and gas. Negative prices are supported; tied extremes select the first
matching interval in the upstream list.

For all three operations, each interval must fall entirely within the
requested Amsterdam calendar day. Overlaps and duplicates are rejected.
`coverage_seconds` sums elapsed interval durations; `expected_seconds`
is the actual local-day duration (82800, 86400 or 90000 seconds for
23-, 24- or 25-hour days). `status` is `empty` when there are no
intervals, `complete` when observed coverage equals the full day,
otherwise `incomplete`. These operations do not claim that upstream
always supplies a full day of prices.

## Consecutive-period contracts

`get_lowest_period` and `get_highest_period` require
`period_minutes: int` and accept optional `day` and `resolution`.
`period_minutes` must be a positive multiple of the resolution step
(15 for `PT15M`, 60 for `PT60M`). For a four-hour period use
`{"period_minutes": 240, "resolution": "PT15M"}`.

The outer response includes `date`, `resolution`, `period_minutes`,
`electricity` and `gas`. Each energy response includes
`period`, `available_interval_count`, `coverage_seconds`,
`expected_seconds` and `status`. `period` is `null` if no qualifying
window exists; otherwise it contains `start`, `end`, `average_total`,
`interval_count` and `unit`.

Candidate windows must contain exactly `period_minutes / step_minutes`
adjacent, full-resolution intervals, with no gaps or overlaps, entirely
inside the requested Amsterdam calendar day. Windows are ranked by the
arithmetic mean of their normalized `total` values; ties select the
earliest chronological window. Results include both electricity and gas,
independently. The tool may return a historical window earlier today;
it does not filter to future intervals. Coverage status describes the
whole day, not whether a matching period was found. DST days use elapsed
UTC duration and never fabricate missing records.

## Best start time contract

`get_best_start_time` requires `period_minutes: int` and accepts optional
`day` (Amsterdam calendar day, default today), `resolution` (default
`PT15M`, also `PT60M`), and `consumption_kwh` (finite non-negative
number). It delegates to the existing cheapest-period selection and uses
**electricity only**. The full requested day is considered, including elapsed
intervals; this is a day-wide optimum, not a guarantee of a future start.

The response includes `date`, `resolution`, `period_minutes`, `start`,
`end`, `average_total`, `unit`, `consumption_kwh`, `estimated_cost`,
`available_interval_count`, `coverage_seconds`, `expected_seconds`,
and `status`. Without a contiguous window, `start`, `end`,
`average_total`, `unit`, and `estimated_cost` are null.
`estimated_cost = average_total * consumption_kwh` assumes a constant
consumption rate across the selected window; no estimate is returned when
consumption is omitted. The price is the upstream normalized total in
currency per kWh, not an independently reconstructed tariff.

## Energy cost estimation contract

`calculate_energy_cost(start, end, consumption_kwh, resolution="PT15M")`
estimates electricity cost for uniform consumption over the requested period.
`start` and `end` must be timezone-aware ISO 8601 datetimes with `end`
strictly later than `start`; `consumption_kwh` must be finite and non-negative.
The supported resolutions are `PT15M` and `PT60M`. The period may cover at
most two consecutive Amsterdam calendar dates. Each relevant normalized
electricity interval must have the requested resolution and provide continuous,
non-overlapping coverage; missing data raises a safe MCP error instead of
returning a partial cost.

The response includes `start`, `end`, `resolution`, `consumption_kwh`,
`average_total`, `estimated_cost`, `unit` (`kWh`), and
`duration_seconds`. `average_total` is weighted by elapsed overlap seconds;
`estimated_cost = average_total * consumption_kwh`. This assumes consumption
is uniform in time. Negative prices are allowed. Timestamp comparisons use UTC
instants and support Amsterdam DST transitions.

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

## Threshold period contract

`get_price_threshold_periods` accepts a finite numeric threshold, `below` or `above` (strict comparisons), an optional Amsterdam calendar date and `PT15M`/`PT60M` resolution. Each energy type returns `periods`, `matching_interval_count`, `interval_count`, `coverage_seconds`, `expected_seconds`, and `status`. Periods report `start`, `end`, `duration_minutes`, `interval_count`, `average_total`, and `unit`. Gaps, nonmatching intervals and invalid-duration bins break groups. Overlapping and out-of-day records are rejected. Empty data yields no periods. Negative prices are supported.
