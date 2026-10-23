# Frank Energie MCP

Standalone Model Context Protocol server built with FastMCP and backed exclusively by [python-frank-energie](https://github.com/HiDiHo01/python-frank-energie).

> **Development status:** The stdio server and MCP registrations exist, but the implementation is not yet production-ready.

## Installation

Requires Python 3.14 or newer.

```bash
python -m pip install -e ".[dev]"
python -m frank_energie_mcp
```

The second command starts the stdio MCP transport. It waits for a compatible MCP client; it is not an interactive terminal interface.

Example client configuration (adapt the Python executable to the environment where the package is installed):

```json
{
  "mcpServers": {
    "frank-energie": {
      "command": "python",
      "args": ["-m", "frank_energie_mcp"]
    }
  }
}
```

## Windows: local Streamable HTTP

Install Python 3.14 or newer, then open PowerShell:

```powershell
git clone https://github.com/HiDiHo01/frank-energie-mcp.git
cd frank-energie-mcp
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:FRANK_ENERGIE_MCP_TRANSPORT = "streamable-http"
$env:FRANK_ENERGIE_MCP_HOST = "127.0.0.1"
$env:FRANK_ENERGIE_MCP_PORT = "8000"
python -m frank_energie_mcp
```

The local MCP endpoint is `http://127.0.0.1:8000/mcp`. This is an MCP protocol endpoint, not a web page; opening it in a browser is not a valid tool test. Test with an MCP-compatible client. The process must remain running while connected.

**Security:** The server binds to loopback only and does not provide inbound authentication. Do not expose this endpoint with router port forwarding, a public reverse proxy, or an unauthenticated tunnel. A ChatGPT connection requires a separately configured, authenticated HTTPS transport/tunnel and compatible ChatGPT custom MCP support; neither is established by these commands. Avoid including account credentials in URLs, scripts, or committed files.

## Implemented MCP registrations

| Kind | Name | Current behavior |
| --- | --- | --- |
| Tool | `get_current_prices` | Returns current electricity and gas intervals via upstream `current_hour` |
| Tool | `get_today_prices` | Fetches today's market prices |
| Tool | `get_tomorrow_prices` | Fetches tomorrow's market prices |
| Tool | `get_average_prices` | Averages available normalized `total` prices for electricity and gas for an optional Amsterdam calendar date and `PT15M`/`PT60M` resolution; reports interval count, first/last timestamps, coverage seconds, and completion status. |
| Tool | `get_lowest_price` | Lowest available normalized total interval per energy type, with coverage status. |
| Tool | `get_highest_price` | Highest available normalized total interval per energy type, with coverage status. |
| Tool | `get_lowest_period` | Finds the cheapest uninterrupted window by average normalized total price. |
| Tool | `get_highest_period` | Finds the most expensive uninterrupted window by average normalized total price. |
| Tool | `get_best_start_time` | Finds the cheapest fully covered start window within optional time bounds. |
| Tool | `calculate_energy_cost` | Estimates constant-power electricity consumption cost over a complete window. |
| Tool | `get_price_threshold_periods` | Groups consecutive intervals strictly below or above a threshold. |
| Tool | `get_negative_price_periods` | Finds consecutive negative-total electricity-price intervals. |
| Tool | `get_price_trend` | Classifies the first-to-last available price change. |
| Tool | `get_price_volatility` | Reports price dispersion and adjacent interval changes. |
| Tool | `compare_days` | Compares two dates' price statistics and mean differences. |
| Tool | `get_best_split_periods` | Selects inexpensive nonoverlapping fixed-length blocks. |
| Tool | `calculate_battery_savings` | Estimates a single idealized battery charge/discharge cycle. |
| Tool | `get_price_statistics` | Reports mean, median, quartiles and dispersion. |
| Tool | `get_gas_price` | Returns the current gas interval or `null` when unavailable |
| Tool | `get_smart_battery_count` | Returns only the number of linked smart batteries; requires credentials. |
| Tool | `get_smart_pv_system_count` | Returns only the number of linked smart PV systems; requires credentials. |
| Tool | `get_electric_vehicle_count` | Returns only the number of linked Enode vehicles; requires credentials. |
| Tool | `get_account` | Requires credentials and a site reference; returns only `{"authenticated": true}` after a successful account request |
| Tool | `list_sites` | Requires credentials; returns only the number of recognized delivery sites |
| Resource | `frank-energie://capabilities` | Static description of capabilities |
| Prompt | `summarize_energy_prices` | Static instructions for comparing prices |

Price requests use the `Europe/Amsterdam` calendar date. Price tools use the bounded, privacy-safe JSON schema documented in MCP_SPEC.md.

## Daily price statistics

Three tools accept an optional `day` (ISO date, for example `2026-10-25`) and
`resolution` (`PT15M` by default, or `PT60M`):

- `get_average_prices`: arithmetic mean of available normalized `total` values
  independently for electricity and gas. It is not duration-weighted.
- `get_lowest_price`: lowest `total` interval for each energy type.
- `get_highest_price`: highest `total` interval for each energy type.

When `day` is omitted, the tools use the current calendar day in
`Europe/Amsterdam`. They request public prices from `python-frank-energie`;
the MCP layer does not calculate taxes or markups.

Example MCP tool arguments:

```json
{"day": "2026-10-25", "resolution": "PT15M"}
```

Each result contains `date`, `resolution`, `electricity` and `gas`.
Average results contain `average_total`, `interval_count`, `first_interval`,
`last_interval`, `coverage_seconds`, `expected_seconds`, `complete` and
`status`. Minimum/maximum results contain a `price` interval (or `null`),
`interval_count`, `coverage_seconds`, `expected_seconds` and `status`.

`status` is `empty` (no intervals), `incomplete` (partial day) or
`complete` (the entire local calendar day is covered). Missing prices are
never filled in; the average of an empty series is `null`. Overlapping,
duplicate or out-of-day intervals are rejected. Coverage is measured in
elapsed seconds, including 23- and 25-hour daylight-saving transition days.
Minimum and maximum ties select the first interval in the upstream list.
For exact response shapes, see [MCP_SPEC.md](MCP_SPEC.md).

## Consecutive price periods

`get_lowest_period` and `get_highest_period` accept a required
`period_minutes` and optional `day` (default: today in Europe/Amsterdam)
and `resolution` (default: `PT15M`; also `PT60M`).

For example, to find the cheapest four consecutive hours today, call
`get_lowest_period` with:

```json
{"period_minutes": 240, "resolution": "PT15M"}
```

A four-hour window requires 16 consecutive 15-minute intervals, or
4 consecutive 60-minute intervals with `PT60M`. The duration must be
positive and divisible by the chosen resolution (15 or 60 minutes).
The selected window minimizes or maximizes the arithmetic mean of
normalized `total` prices; it is calculated separately for electricity
and gas. Each result includes `period` (or `null` if no uninterrupted
window exists), `available_interval_count`, `coverage_seconds`,
`expected_seconds`, and `status`. The period includes `start`, `end`,
`average_total`, `interval_count`, and `unit`.

Only fully contained, contiguous windows are considered; gaps are not
filled. The search uses the entire requested calendar day and does not
restrict today's result to future intervals. Equal averages prefer the
earliest window. See [MCP_SPEC.md](MCP_SPEC.md).

## Optimization tools

Five additional read-only tools use normalized public `total` prices:

| Tool | Parameters | Result |
| --- | --- | --- |
| `get_best_start_time` | `duration_minutes`, optional `day`, `resolution`, `earliest_start`, `latest_end` | Cheapest fully covered consecutive interval window per energy type, or `null` |
| `calculate_energy_cost` | `power_kw`, `duration_minutes`, `start_time`, optional `resolution` | Constant-power electricity estimate in kWh and currency-per-kWh × kWh; `incomplete` if any bin is missing |
| `get_price_threshold_periods` | `threshold`, optional `below`, `minimum_duration_minutes`, `day`, `resolution` | Consecutive groups strictly below/above the price threshold for electricity and gas |
| `get_best_split_periods` | `total_minutes`, `minimum_block_minutes`, optional `day`, `resolution` | Cheapest nonoverlapping fixed-size blocks; all blocks must be available |
| `calculate_battery_savings` | `capacity_kwh`, `charge_power_kw`, `discharge_power_kw`, `round_trip_efficiency`, optional `day`, `resolution` | Estimated one-cycle charge-before-discharge price arbitrage for electricity |

Dates default to today in `Europe/Amsterdam`. Datetime inputs must
include a UTC offset. All durations are in minutes and must be divisible
by the selected resolution. The electricity cost estimator requires the
entire requested interval to fit within one local calendar day.
`get_best_split_periods` selects whole fixed-length blocks; it does
not model partial or interruptible loads within blocks.

The battery calculation is a **simplified estimate**, not a dispatch
optimizer: it assumes one charge/discharge cycle, constant price per
interval, idealized energy transfer at the specified round-trip
efficiency, and no standing charges, battery degradation, export
restrictions, household demand profile or dynamic power throttling.
Do not use it as a guaranteed savings forecast.

## Practical MCP tool calls

The following are example tool **arguments**, not live prices. The MCP client
invokes the named tool; these JSON objects are not shell commands.

**Find the cheapest four consecutive hours:**

```json
{"period_minutes": 240, "day": "2026-10-23", "resolution": "PT15M"}
```

Tool: `get_lowest_period`.

**Find a two-hour low-cost start window after 10:00 local time:**

```json
{
  "duration_minutes": 120,
  "day": "2026-10-23",
  "resolution": "PT15M",
  "earliest_start": "2026-10-23T10:00:00+02:00",
  "latest_end": "2026-10-23T23:00:00+02:00"
}
```

Tool: `get_best_start_time`.

**Estimate a 2 kW appliance running for one hour:**

```json
{
  "power_kw": 2.0,
  "duration_minutes": 60,
  "start_time": "2026-10-23T12:00:00+02:00",
  "resolution": "PT15M"
}
```

Tool: `calculate_energy_cost`. A full set of price intervals is required;
an incomplete window produces `status: "incomplete"` and null costs.

**Find periods strictly cheaper than 0.20 per kWh (electricity) or
per m³ (gas):**

```json
{"threshold": 0.2, "below": true, "minimum_duration_minutes": 30}
```

Tool: `get_price_threshold_periods`. The same numeric threshold is applied
independently to both energy types; units differ.

**Find negative electricity-price periods:**

```json
{"minimum_duration_minutes": 30, "resolution": "PT15M"}
```

Tool: `get_negative_price_periods`. Zero does not qualify.

**Select four hours as two independent two-hour blocks:**

```json
{"total_minutes": 240, "minimum_block_minutes": 120}
```

Tool: `get_best_split_periods`. Block selection is greedy, not a general
globally optimal scheduling algorithm.

**Estimate one battery charge/discharge cycle:**

```json
{
  "capacity_kwh": 5.0,
  "charge_power_kw": 2.5,
  "discharge_power_kw": 2.5,
  "round_trip_efficiency": 0.9
}
```

Tool: `calculate_battery_savings`. The model is simplified and does not
account for actual household consumption, degradation, or grid fees.

**Compare two calendar days:**

```json
{"first_day": "2026-10-22", "second_day": "2026-10-23"}
```

Tool: `compare_days`. `mean_difference` is second day minus first day;
missing prices are not imputed.

**Inspect trend, volatility and descriptive statistics:** use
`get_price_trend`, `get_price_volatility`, or `get_price_statistics`
with `{"day": "2026-10-23", "resolution": "PT15M"}`. Trend also accepts
`stable_tolerance` (absolute price units, default 0.005).

## Additional daily price analytics

The existing `get_price_threshold_periods`, `get_best_split_periods`
and `calculate_battery_savings` remain available; they are not
registered twice. Five further tools are available:

| Tool | Behavior |
| --- | --- |
| `get_negative_price_periods` | Contiguous electricity intervals strictly below zero, with configurable minimum duration |
| `get_price_trend` | First-to-last available price change classified as rising, falling or stable with an absolute tolerance |
| `get_price_volatility` | Population standard deviation, range and changes between adjacent available intervals |
| `compare_days` | Compares price distributions on two dates and returns the second-minus-first mean difference |
| `get_price_statistics` | Mean, median, minimum, maximum, range, population standard deviation and interpolated 25th/75th percentiles |

All operations use normalized public `total` values, with separate
electricity and gas results except negative-price periods, which apply
only to electricity. Empty data returns null statistics; trend results
also report whether any gaps exist. Comparison statistics describe
available intervals, not guaranteed complete-day coverage.

## Linked-device tools from the upstream API

The upstream `python-frank-energie` client exposes
`smart_batteries()`, `smart_pv_systems()` and `enode_vehicles()`.
Three read-only MCP tools wrap these methods and return only
`{"count": N}`. No device IDs, addresses, charging settings, or
other identifying metadata are returned.

- `get_smart_battery_count`: linked smart battery count.
- `get_smart_pv_system_count`: linked solar PV system count.
- `get_electric_vehicle_count`: linked Enode electric vehicle count.

All three require `FRANK_ENERGIE_USERNAME` and
`FRANK_ENERGIE_PASSWORD` in the server environment. Some upstream
services also require smart-trading or smart-charging enrollment.
A count of zero does not establish that the account is eligible for
a particular feature. API failures are returned as generic MCP errors.

Other upstream capabilities inspected include invoices, meter readings,
month insights, customer-specific prices, contract price resolution,
battery sessions, solar summaries and charging controls. These are
not exposed here because they require additional privacy, input and
write-action policy design. The three new tools perform no mutations.

## Authentication

Account and delivery-site tools use the existing upstream `python-frank-energie` login method. Configure the server process with `FRANK_ENERGIE_USERNAME` and `FRANK_ENERGIE_PASSWORD`; set `FRANK_ENERGIE_SITE_REFERENCE` for `get_account`. Both credentials must be provided together. Missing credentials or site references cause descriptive errors before an account request is sent. Avoid putting credentials in repository files, command-line arguments, logs or screenshots. The server currently logs in for each managed upstream session and closes the client after each request. Token persistence, renewal across requests and credential rotation have not been validated.

## Architecture

```text
MCP client
    |
FastMCP stdio server (server.py)
    |
FrankEnergieService (library.py)
    |
FrankEnergieLibraryBridge (managed async client)
    |
python-frank-energie
    |
Frank Energie API
```

API communication, authentication and price calculations belong in the upstream library, not in the MCP server.

## Validation

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest -q
```

Tests use mock clients; they do not require production credentials. These commands are documented checks, not a claim that CI currently passes.

## Known limitations

- Environment-based login and explicit site-reference selection are implemented; persistent token lifecycle and operational validation remain pending.
- Normalized price responses and generic error mapping have unit coverage; real upstream and MCP transport interoperability still require validation.
- End-to-end MCP client interoperability has not been validated.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MCP_SPEC.md](MCP_SPEC.md), [AI_POLICY.md](AI_POLICY.md) and [SECURITY.md](SECURITY.md). Do not commit credentials or personal account data.

## Production deployment gates

**Local Windows (stdio):** Install into a dedicated Python 3.14 virtual environment, run the four validation commands above, and configure the MCP client to launch the virtual-environment Python executable. Keep credentials in the process environment or a protected secret store. Do not store them in client configuration committed to Git.

**External ChatGPT access:** Not production-ready yet. The built-in Streamable HTTP listener is **loopback-only and unauthenticated**. Do not expose it publicly or treat a TLS tunnel alone as sufficient authentication. A production deployment needs an HTTPS ingress with validated client authentication and authorization, restricted access to the upstream loopback service, rate limiting, request/body size limits, TLS certificate management, and documented token rotation. Verify that the intended ChatGPT MCP connector supports the chosen authentication flow before deployment. A reverse proxy or tunnel must not forward unauthenticated public requests to `/mcp`.

**Release blockers:** Verify all CI checks on the exact release commit; review legacy unused models and modules; validate real MCP tool calls over both transports; test upstream timeouts, authentication failures, missing data, and time-zone boundaries; and document a rollback procedure. Do not describe the service as production-ready until these checks pass.
