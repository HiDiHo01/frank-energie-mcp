# MCP Specification

## Implementation status

The server uses the official Python MCP SDK's FastMCP runtime. Thirty-eight read-only asynchronous tools, one static resource, and one static prompt are registered. The interface remains under development and is not yet production-ready.

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
| `get_highest_period` | `get_highest_period(period_minutes, day, resolution)` | Most expensive uninterrupted fixed-duration window, with the same response contract. |
| `get_best_start_time` | `get_best_start_time(duration_minutes, day, resolution, earliest_start, latest_end)` | Per-energy cheapest uninterrupted window or `null` |
| `calculate_energy_cost` | `calculate_energy_cost(power_kw, duration_minutes, start_time, resolution)` | Electricity `status`, `cost`, `energy_kwh` |
| `get_price_threshold_periods` | `get_price_threshold_periods(threshold, below, minimum_duration_minutes, day, resolution)` | Per-energy arrays of qualifying periods |
| `get_negative_price_periods` | `get_negative_price_periods(day, resolution, minimum_duration_minutes)` | Electricity-only array of negative-price periods |
| `get_price_trend` | `get_price_trend(day, resolution, stable_tolerance)` | Per-energy direction, change and gap indicator |
| `get_price_volatility` | `get_price_volatility(day, resolution)` | Per-energy dispersion and adjacent changes |
| `compare_days` | `compare_days(first_day, second_day, resolution)` | Two days of per-energy statistics and mean differences |
| `get_best_split_periods` | `get_best_split_periods(total_minutes, minimum_block_minutes, day, resolution)` | Per-energy selected blocks and status |
| `calculate_battery_savings` | `calculate_battery_savings(capacity_kwh, charge_power_kw, discharge_power_kw, round_trip_efficiency, day, resolution)` | Electricity one-cycle estimate and assumptions |
| `get_price_statistics` | `get_price_statistics(day, resolution)` | Per-energy descriptive statistics |
| `get_gas_price` | `get_gas_price(resolution)` | Normalized active gas interval or `null` |
| `get_smart_battery_count` | `get_smart_battery_count()` | Authenticated `{"count": N}` from upstream `smart_batteries()` |
| `get_smart_pv_system_count` | `get_smart_pv_system_count()` | Authenticated `{"count": N}` from upstream `smart_pv_systems()` |
| `get_electric_vehicle_count` | `get_electric_vehicle_count()` | Authenticated `{"count": N}` from upstream `enode_vehicles()` |
| `get_smart_feed_in_status` | `get_smart_feed_in_status()` | Authenticated, allowlisted boolean enrollment flags |
| `get_contract_price_resolution_state` | `get_contract_price_resolution_state(connection_id)` | Authenticated, allowlisted contract resolution options |
| `get_invoice_statistics` | `get_invoice_statistics(year)` | Authenticated annual invoice count, total and average |
| `get_smart_pv_system_summary` | `get_smart_pv_system_summary(device_id)` | Authenticated, allowlisted PV status and totals |
| `get_smart_battery_status` | `get_smart_battery_status(device_id)` | Authenticated battery charge, status, update timestamp and capacity |
| `get_smart_hvac_status` | `get_smart_hvac_status()` | Authenticated HVAC activation and country-availability flags |
| `get_daily_consumption_statistics` | `get_daily_consumption_statistics(start_date, end_date)` | Authenticated daily kWh count, total and average over an inclusive range |
| `get_smart_battery_session_statistics` | `get_smart_battery_session_statistics(device_id, start_date, end_date)` | Authenticated session count and aggregate trading results |
| `get_period_usage_and_costs` | `get_period_usage_and_costs(start_date)` | Authenticated billing-period usage and cost totals by energy category |
| `get_ev_charger_statistics` | `get_ev_charger_statistics(start_date)` | Authenticated EV charger reachability and smart charging counts |
| `get_monthly_cost_insights` | `get_monthly_cost_insights(month)` | Authenticated monthly expected and actual cost totals |
| `get_account_country` | `get_account_country()` | Authenticated two-letter account country code |
| `get_smart_battery_fleet_statistics` | `get_smart_battery_fleet_statistics()` | Aggregate linked battery capacity and rated power |
| `get_electric_vehicle_statistics` | `get_electric_vehicle_statistics()` | Authenticated vehicle reachability and smart charging counts |
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

## Optimization tool contracts

The server also registers `get_best_start_time`,
`calculate_energy_cost`, `get_price_threshold_periods`,
`get_best_split_periods`, and `calculate_battery_savings`.
All operate on normalized `total` values from one upstream
`prices(day, resolution=...)` call, without recomputing tax or markup.

Time windows must contain contiguous, full-resolution intervals and
fit within the selected Amsterdam calendar day. `get_best_start_time`
returns the cheapest window for each energy type (or `null`); optional
aware `earliest_start` and `latest_end` restrict candidate windows.
`calculate_energy_cost` returns `status`, `cost`, and
`energy_kwh` for a constant electrical power; incomplete data yield
null amounts. `get_price_threshold_periods` returns arrays of
strictly qualifying contiguous periods. `get_best_split_periods`
returns `status`, `periods`, and `average_total`; missing complete
blocks produce `incomplete`. The split selection is a cheapest-first
block heuristic, not a globally optimal solution for arbitrary
scheduling constraints.

`calculate_battery_savings` returns a `status`, optional `cycle`,
and explicit `assumptions`. The cycle contains charge/discharge
windows, charge cost, avoided discharge cost, and estimated savings.
It is an idealized single-cycle model, without a load profile, grid
fees, battery wear or export modeling; results may be negative.
The battery power limits are approximated at whole-resolution windows.

## Additional analytics contracts

`get_negative_price_periods(day=None, resolution="PT15M",
minimum_duration_minutes=15)` returns electricity periods strictly
below zero. `get_price_trend(day=None, resolution="PT15M",
stable_tolerance=0.005)` classifies the difference between the last
and first available normalized total; its direction is `rising`,
`falling`, `stable` or `insufficient_data`. It also reports gaps.
`get_price_volatility` returns population standard deviation, spread,
largest adjacent increase/decrease and mean absolute adjacent change;
nonadjacent intervals are excluded from difference calculations.
`get_price_statistics` returns count, mean, median, minimum, maximum,
range, population standard deviation and linearly interpolated p25/p75.
`compare_days(first_day, second_day, resolution="PT15M")` returns
both days' statistics and second-minus-first mean differences for each
energy type. Empty datasets produce null statistics; these functions
do not impute missing prices.

## Parameter and response reference

- `day` defaults to today's calendar date in `Europe/Amsterdam`;
  `first_day` and `second_day` are required ISO calendar dates.
- `resolution` is `PT15M` (15-minute bins) or `PT60M` (hourly bins).
  Window durations must be positive multiples of that bin size.
- `earliest_start`, `latest_end`, and `start_time` require timezone-aware
  ISO timestamps. A requested cost window must fit within one local day.
- `below=true` means strictly less than the threshold; `below=false`
  means strictly greater. Negative-price periods are strictly below zero.
- `stable_tolerance` is a nonnegative absolute difference in the upstream
  price unit. Trend classification compares the first and last *available*
  interval, not a fitted regression slope.
- `get_price_statistics` uses population standard deviation and linearly
  interpolated p25/p75. Missing datasets return `count=0` and null
  descriptive values.
- `get_price_volatility` only calculates changes between immediately
  adjacent price intervals. Gaps do not contribute changes.
- `get_best_split_periods` uses cheapest-first, fixed-size nonoverlapping
  blocks; `total_minutes` must be divisible by `minimum_block_minutes`.
  This heuristic is not a general constrained scheduling optimizer.
- `calculate_battery_savings` assumes one charge-before-discharge cycle
  and simplified full-bin power constraints. The response is an estimate,
  not a guaranteed bill saving.

For all daily analytics, electricity and gas prices have different physical
units; their numeric results should not be combined. The normalized `total`
comes from upstream data. The server does not independently derive taxes,
markups or supplier-specific billing terms.

## Authenticated device-count contracts

The three device-count tools have no arguments. They require server-side
Frank Energie credentials and return only a nonnegative integer count
in `{"count": N}`. They call the upstream `smart_batteries()`,
`smart_pv_systems()` and `enode_vehicles()` methods, respectively.
A `None` upstream result is represented as zero; unexpected collection
shapes raise an error. Raw device objects, IDs and account metadata
are never serialized into MCP responses. These operations are read-only.

## Additional authenticated status contracts

`get_smart_feed_in_status()` returns `available` and four
allowlisted boolean flags: `is_activated`, `has_accepted_terms`,
`is_app_onboarding_available`, `is_available_in_country`. When the
upstream response is null, flags are null and `available=false`.

`get_contract_price_resolution_state(connection_id)` requires a
nonempty connection ID, returns `available`, `active_option`,
`available_options` and `is_change_request_possible`. A null
upstream state yields `{"available": false}`. Neither endpoint
returns user IDs, connection IDs or raw upstream account objects.
No contract-changing API method is exposed.

## Annual invoices and PV status contracts

`get_invoice_statistics(year)` accepts an integer from 2000 through
2100. It requires credentials and a configured site reference.
The result contains `year`, `invoice_count`, `total_amount`
and `average_amount` (null if no invoices qualify). The year is
determined from each upstream invoice start date converted to the
Amsterdam timezone. Invoice identifiers and descriptions are excluded.

`get_smart_pv_system_summary(device_id)` requires credentials and
a nonempty device ID. It returns only `available`,
`operational_status`, `steering_status`, `total_bonus` and
`total_result`. Missing upstream summaries return
`{"available": false}`. Neither method writes upstream state.

## Smart battery status contract

`get_smart_battery_status(device_id)` requires credentials and a
nonempty device ID. It returns `available`,
`state_of_charge_percent`, `status`, `last_update`, and
`capacity_kwh`. Charge is validated as an integer in 0–100,
capacity is nonnegative and finite when provided, and timestamps
must be timezone-aware. A null upstream detail result returns
`{"available": false}`. The response excludes device identifiers
and configuration, and never invokes upstream write operations.

## Smart HVAC status contract

`get_smart_hvac_status()` requires Frank Energie credentials. It
returns `available: bool`, `is_activated: bool | null`, and
`is_available_in_country: bool | null`. Null upstream enrollment
produces `available=false` with null flags. User identifiers and
creation timestamps are excluded; no HVAC mutation is invoked.

## Daily consumption statistics contract

`get_daily_consumption_statistics(start_date, end_date)` accepts
two ISO calendar dates, inclusive, with `end_date >= start_date`
and a maximum span of 366 days. It requires credentials and a
configured delivery-site reference. It returns `start_date`,
`end_date`, `day_count`, `total_kwh` and
`average_daily_kwh` (null for zero observed days).
Only upstream days present in the requested range are aggregated;
missing days do not count as zero. User identifiers and individual
readings are not returned. The operation is read-only.

## Battery trading-session statistics contract

`get_smart_battery_session_statistics(device_id, start_date, end_date)`
requires credentials, a nonempty device ID, and an inclusive
ordered date range no longer than 366 days. It returns
`available`, `session_count`, `result_count`,
`total_session_result` and `average_session_result`.
Null session results are omitted from the aggregate; missing
or empty results produce null total and average. Nonfinite
results are rejected. Device identifiers and individual
trading sessions are excluded. No upstream mutation is called.

## Billing-period usage and costs contract

`get_period_usage_and_costs(start_date)` requires credentials,
a configured delivery-site reference, and an ISO calendar date.
It returns `available`, `start_date`, and when available
`categories` containing `electricity`, `gas`, and `feed_in`
with `unit`, `usage_total`, and `costs_total`.
Missing categories are null; missing periods return
`{"available": false, "start_date": "..."}`.
Nonfinite totals and invalid units are rejected. Raw period
identifiers, individual usage items and customer data are omitted.
No upstream write operation is invoked.

## EV charger statistics contract

`get_ev_charger_statistics(start_date)` requires credentials,
a configured delivery-site reference, and an ISO calendar date.
It returns nonnegative integer counts: `charger_count`,
`reachable_count`, `smart_capable_count`, and
`smart_enabled_count`. Invalid boolean capability fields
are rejected. Device IDs, intervention records, and raw
charging settings are excluded. No upstream mutation is called.

## Monthly cost insights contract

`get_monthly_cost_insights(month)` accepts a strictly formatted
`YYYY-MM` calendar month and requires credentials and a site
reference. It delegates to upstream `month_insights` and
returns `available`, `month`, and the seven allowlisted
expected/actual cost fields. Absent upstream data produces
`available=false`. Nonfinite values are rejected.
Invoice identifiers, personal metadata and raw model data
are excluded. This tool is read-only.

## Account country contract

`get_account_country()` requires account credentials and calls
upstream `user_country()`. It returns exactly one field,
`country_code`, containing a validated uppercase two-letter
ASCII code. Invalid or missing codes are rejected. User IDs,
email addresses and other account details are not returned.
A site reference is not required. The tool is read-only.

## Smart battery fleet statistics contract

`get_smart_battery_fleet_statistics()` requires credentials
and calls upstream `smart_batteries()`. It returns the total
battery count, number with reported capacity, summed capacity
in upstream kWh, and summed maximum charge/discharge power
in upstream units. Missing values are excluded, and totals
without observations are null. Nonfinite or negative values
are rejected. Device identifiers and configuration are excluded.
No battery mutations are invoked.

## Electric vehicle statistics contract

`get_electric_vehicle_statistics()` requires credentials and
delegates to upstream `enode_vehicles()`. It returns integer
counts for linked, reachable, smart-charge-capable and
smart-charging-enabled vehicles. Invalid boolean flags are
rejected. Vehicle identifiers and settings are excluded.
A site reference is not required. No upstream write is called.

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
