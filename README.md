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
| Tool | `get_gas_price` | Returns the current gas interval or `null` when unavailable |
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
