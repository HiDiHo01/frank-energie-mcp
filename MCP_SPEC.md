# MCP Specification

## Implementation status

The server uses the official Python MCP SDK's FastMCP runtime. Twenty-seven read-only asynchronous tools, one static resource, and one static prompt are registered. The interface remains under development and is not yet production-ready.

## Transports

`python -m frank_energie_mcp` starts stdio by default. Set `FRANK_ENERGIE_MCP_TRANSPORT=streamable-http` to start Streamable HTTP at `http://127.0.0.1:8000/mcp` by default. The HTTP host must be `127.0.0.1`; `FRANK_ENERGIE_MCP_PORT` must be an integer from 1 to 65535. Unsupported transports are rejected.

The HTTP listener has no application-level inbound authentication. Do not expose it publicly, through port forwarding, or through an unauthenticated proxy or tunnel. The effective SDK origin/DNS-rebinding protections have not been independently verified.

## Tools

All price tools accept an optional `resolution` parameter: `PT15M` (default) or `PT60M`. Other values are rejected by the MCP tool schema.

| Tool | Service operation | Current response |
| --- | --- | --- |
| `get_charging_efficiency_analysis` | `get_charging_efficiency_analysis(energy_kwh, max_power_kw, start, deadline, efficiencies, allow_interruptions, resolution)` | Compare 1–12 unique finite efficiencies within (0, 1] using the existing optimal charging planner. Reports required grid kWh, losses, slot count, feasible schedule, estimated cost, and difference from the cheapest feasible scenario. Unavailable prices yield null costs. |
| `get_charging_power_analysis` | `get_charging_power_analysis(energy_kwh, power_levels_kw, start, deadline, efficiency, allow_interruptions, resolution)` | Compare 1–12 unique positive finite charging power levels against the same timezone-aware window. Returns each planner status, required grid energy and slot count, schedule, estimated cost, and extra cost relative to the cheapest feasible power level. Missing prices produce null costs; does not extrapolate prices. |
| `get_current_prices` | `get_current_prices(resolution)` | Object with `electricity` and `gas` active upstream `current_hour` intervals, each a normalized record or `null` |
| `get_today_prices` | `get_today_prices(resolution)` | Normalized `electricity` and `gas` interval arrays from `prices(today, resolution=...)` |
| `get_tomorrow_prices` | `get_tomorrow_prices(resolution)` | Normalized interval arrays from `prices(tomorrow, resolution=...)` |
| `compare_days` | `compare_days(first_day, second_day, resolution)` | Per-energy observed average/minimum/maximum normalized all-in totals for both local days, absolute and percentage differences, and DST-aware coverage metadata. |
| `get_average_prices` | `get_average_prices(day, resolution)` | Per-energy average of all available normalized `total` values, interval count, first/last timestamps, observed and expected coverage seconds, and `empty`/`incomplete`/`complete` status. `day` defaults to today in Europe/Amsterdam. Overlaps and out-of-day intervals are rejected. |
| `get_lowest_price` | `get_lowest_price(day, resolution)` | Minimum total interval for each energy type, with coverage metadata. |
| `get_highest_price` | `get_highest_price(day, resolution)` | Maximum total interval for each energy type, with coverage metadata. |
| `get_best_split_periods` | `get_best_split_periods(total_duration_minutes, block_duration_minutes, day, resolution)` | Lowest-cost non-overlapping fixed-length blocks for electricity and gas, including coverage status and price metrics. |
| `get_lowest_period` | `get_lowest_period(period_minutes, day, resolution)` | Cheapest uninterrupted fixed-duration window for electricity and gas, selected by arithmetic mean of normalized `total`. |
| `calculate_battery_savings` | `calculate_battery_savings(capacity_kwh, charge_power_kw, discharge_power_kw, charge_efficiency, discharge_efficiency, day, resolution)` | Best estimated one-charge-interval/one-discharge-interval self-consumption arbitrage cycle, or null for incomplete coverage. |
| `get_price_volatility` | `get_price_volatility(day, resolution)` | Per-energy all-in price spread, population standard deviation, and mean absolute change across only contiguous intervals, with coverage metadata. |
| `get_price_trend` | `get_price_trend(day, resolution)` | Per-energy first-to-last normalized total-price change, rising/falling/stable/unknown direction, and daily coverage metadata. |
| `get_negative_price_periods` | `get_negative_price_periods(day, resolution)` | Convenience wrapper for strict negative total-price intervals, returning the threshold-period response for electricity and gas. |
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

`get_negative_price_periods` delegates to `get_price_threshold_periods(threshold=0.0, comparison="below")`. Zero-price intervals are excluded; the returned date, resolution, coverage metadata, and period fields use the same contract. It requires no credentials and does not perform an additional API request.

`get_price_trend` compares the earliest and latest available normalized total-price intervals for the selected local date. Equal values are `stable`; one or zero intervals yield `unknown`. The tool reports coverage separately and does not infer missing prices or forecast beyond the selected day.

`get_price_volatility` calculates the population standard deviation of observed normalized total prices. The mean absolute change excludes pairs separated by missing intervals. A single interval yields zero spread/deviation but no adjacent-change estimate; empty datasets return null metrics. Coverage is reported separately, without imputing missing intervals.

`compare_days` reports the second day's price minus the first day's price. Percentage changes use the absolute value of the first day's price as denominator; they are null when the baseline is zero or either day has no observations. Each day is validated independently for gaps, overlaps and DST-aware calendar boundaries. Incomplete coverage is flagged, not filled.

`get_best_split_periods` selects globally cheapest non-overlapping blocks of a fixed length; block and total durations must be positive resolution multiples, with total divisible by block duration. It excludes missing intervals and does not fabricate prices. `total_cost_per_unit` is the sum of each selected block's average total price multiplied by its duration in hours (cost for a constant load of one energy unit per hour); it is not a household cost estimate. Selection is null if the requested schedule cannot be fulfilled.

`calculate_battery_savings` is a conservative **single-cycle, single-interval charge then single-interval discharge** estimate, not a full battery dispatch optimization. It assumes an initially empty battery, sufficient consumption during discharge to avoid retail purchases, no export remuneration, no fixed charges, no battery degradation cost, and no carryover across days. Both efficiency parameters must be in (0, 1]. Only complete local-day price coverage produces a numerical savings estimate; zero means no profitable cycle. Negative all-in prices are supported. All-in price units are currency per kWh, and the estimate is in the corresponding currency.

### `get_price_statistics`

`get_price_statistics(day=None, resolution="PT15M")` returns electricity and gas statistics over the **observed** intervals: duration-weighted mean, population variance, standard deviation, minimum, maximum, median and percentiles P10/P25/P75/P90. Percentiles use the **duration-weighted nearest-rank** method (first price where cumulative observed duration reaches the percentile); they are not interpolated. Counts of negative/zero intervals and their durations are included. Missing intervals are never imputed: `coverage_status`, `coverage_seconds`, `expected_seconds`, and `complete` expose completeness, including 23/25-hour Amsterdam DST days. Empty series have null numeric statistics. Price unit is the normalized upstream unit, and totals are all-in prices.

### `get_price_forecast_summary`

`get_price_forecast_summary(day=None, resolution="PT15M", period_minutes=60)` fetches public all-in electricity and gas prices for the requested Amsterdam calendar day (default: today) and its following day (tomorrow). For each energy type it returns the observed average, minimum, maximum, interval count, DST-aware coverage status and seconds, and cheapest/dearest **contiguous** windows of the requested duration. `average_difference` is tomorrow minus today and is null if either has no data. Missing tomorrow prices are marked empty, never predicted or filled. `period_minutes` must be a positive multiple of the selected resolution (15 or 60 minutes), up to 1500 minutes. Windows require uninterrupted, resolution-sized intervals; incomplete days remain marked incomplete.

### `get_optimal_charging_schedule`

`get_optimal_charging_schedule(energy_kwh, max_power_kw, start, deadline, efficiency=1.0, allow_interruptions=true, resolution="PT15M")` calculates a fixed-power, least-cost charging schedule using only published all-in electricity prices. `start` and `deadline` must be timezone-aware datetimes, with a positive window of at most 48 hours. Energy is delivered energy (kWh), max power is grid draw (kW), and efficiency is in (0, 1]. The planner selects full resolution-sized price slots wholly inside the window, with a possible partial-energy final slot, without inferring missing prices. Interruptible schedules select the cheapest slots; uninterrupted schedules select the cheapest contiguous block. Returns `status=insufficient_prices` with a null cost and empty schedule if the required slots cannot be scheduled. A fixed maximum charging power is assumed; partial-energy slots are costed proportionally but represented with full slot start/end bounds. The result is a price optimization, not a command to a charger.

### `compare_charging_strategies`

`compare_charging_strategies(energy_kwh, max_power_kw, start, deadline, efficiency=1.0, resolution="PT15M")` compares immediate charging (earliest full-price slots), the cheapest contiguous schedule, and the cheapest interruptible schedule. All three delegate to `get_optimal_charging_schedule`, using the same fixed-power model, published all-in electricity prices and timezone-aware bounds. The response includes each plan, its cost or null for insufficient data, and absolute/percentage savings versus immediate charging. Savings percentages use the absolute baseline cost as denominator and are null if baseline is zero or missing. An immediate schedule that cannot finish by the deadline is unavailable. This is a planning tool, not a charger-control service.

### `get_charging_deadline_analysis`

`get_charging_deadline_analysis(energy_kwh, max_power_kw, start, deadlines, efficiency=1.0, allow_interruptions=true, resolution="PT15M")` compares the existing fixed-power charging planner for 1–12 unique, timezone-aware deadlines, each within 48 hours of the start. Results preserve the caller's deadline order and include each deadline's status, estimated cost, schedule and extra cost versus the lowest available cost. If no deadline is feasible with published prices, the lowest cost and all differences are null. A missing-price schedule is not estimated. No charger commands are issued.
