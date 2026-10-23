# Architecture

## Overview

Frank Energie MCP is a standalone, read-only Model Context Protocol server built with FastMCP. It delegates Frank Energie API access and domain logic to `python-frank-energie`. The MCP layer is responsible for transport, tool registration, input validation, and privacy-aware response shaping.

```text
MCP client
    |
    | stdio (default) or loopback Streamable HTTP
    v
server.py: FastMCP tool/resource/prompt registration
    |
    | safe_tool_call: generic errors, exception-class-only logging
    v
library.py: FrankEnergieService
    |
    | managed async session, optional environment-based login
    v
library.py: FrankEnergieLibraryBridge
    |
    v
python-frank-energie
    |
    v
Frank Energie API

For price results:
FrankEnergieService -> price_schemas.py -> JSON-compatible public fields
For account/site results:
FastMCP handlers -> minimal AccountResponse / SitesResponse
```

## Current modules

| Module | Responsibility |
| --- | --- |
| `__main__.py` | Invokes `server.main()` |
| `server.py` | FastMCP creation, twenty-one tool registrations, resource, prompt, safe tool error handling, transport configuration, and minimal account/site responses |
| `library.py` | `FrankEnergieService`, typed upstream protocol, managed `FrankEnergieLibraryBridge`, environment configuration, and active-interval selection |
| `price_schemas.py` | Strict Pydantic price models, explicit field whitelisting, timestamp/amount validation, JSON normalization, and array bounds |
| `tools/__init__.py` | Legacy package retained for import compatibility; tool implementations now live in `server.py` |
| `models.py` | Legacy generic dataclasses; not the active price response contract |

Separate `auth.py`, `config.py`, `resources/`, and `prompts/` implementations are not part of the current runtime architecture. Authentication and configuration are in `library.py`; the resource and prompt are registered in `server.py`.

## Responsibilities and boundaries

### MCP layer

- Expose twenty-one asynchronous read-only tools, one static resource, and one static prompt.
- Validate `resolution` as `PT15M` or `PT60M` at the tool boundary.
- Use `Europe/Amsterdam` dates for today/tomorrow and optional-date statistical price requests.
- Select upstream `current_hour` records for current electricity/gas prices.
- Normalize market prices to explicitly permitted public fields; do not serialize raw upstream models.
- Reuse normalized `total` values for arithmetic averages and extrema; never reimplement upstream taxes or markups.
- Check interval containment, overlaps and elapsed coverage against local-day boundaries for statistical tools.
- Return only authentication status for account calls and site count for site calls.
- Convert tool failures into generic client errors without logging upstream exception messages.

### Upstream library

`python-frank-energie` owns authentication operations, GraphQL/API communication, price calculations, domain models, and upstream error behavior. The MCP layer must not duplicate these responsibilities.

## Request lifecycle

1. FastMCP validates the tool name and any `resolution` argument.
2. The tool handler invokes a method on `FrankEnergieService` through `safe_tool_call`.
3. `FrankEnergieLibraryBridge.session()` constructs the upstream client, logs in if both credentials are configured, and yields it.
4. The service calls upstream `prices(date, resolution=...)`, `user(site_reference)`, or `UserSites()`, as appropriate.
5. The session closes the upstream client in a `finally` block, including on errors.
6. Price results are normalized by `price_schemas.py`; account and site results are reduced to minimal public response models in `server.py`.
7. FastMCP returns the response, or a generic `ToolError` on handled failures.

Price interval normalization requires ordered timezone-aware timestamps, finite numeric totals, and no more than 200 intervals per energy type for full-day results. This is a defensive MCP response-size limit, **not** an upstream API limit. The upstream library supports `PT15M` and `PT60M`; complete Europe/Amsterdam days produce 92/96/100 or 23/24/25 intervals respectively, including DST transitions. The cap allows headroom and does not assert that upstream always returns complete days.

## Daily statistics data flow

The three daily statistics tools share the same upstream call and normalized
interval contract. The service requests `prices(day, resolution=...)`, passes
the result through `normalize_market_prices`, then operates independently on
electricity and gas records. `get_average_prices` computes an unweighted
arithmetic mean of available `total` values. `get_lowest_price` and
`get_highest_price` select the interval with the extreme normalized `total`.
The minimum/maximum operations reuse the average helper's interval chronology
and coverage validation, rather than duplicating this logic.

The coverage validator compares aware UTC instants against the boundaries of
the requested `Europe/Amsterdam` calendar day. This accounts for daylight
saving transitions and reports `empty`, `incomplete`, or `complete`
without assuming the API returns every interval. It rejects overlaps,
duplicates and intervals outside the requested day. The current
implementation selects the first upstream record on equal extrema and
does not weight average prices by interval duration.

## Consecutive-window selection

The service fetches one normalized public price series for the selected
Amsterdam date. Both `get_lowest_period` and `get_highest_period` use
the same window-selection helper and reuse the existing interval chronology
and day-coverage validation. Candidate windows must consist of adjacent
15- or 60-minute records, with the requested total elapsed duration.
The ranking uses the mean normalized `total` price; no tax or markup
logic is duplicated. Missing intervals invalidate affected windows,
while other complete windows remain eligible. The algorithm returns
`null` when no complete window exists, and prefers the earliest window
for tied averages.

## Price optimization

`optimization.py` is a pure, reusable calculation layer over
privacy-filtered `PriceInterval` records. It validates timestamp
containment, expected 15-/60-minute interval lengths, overlaps,
continuity, and parameter ranges before selecting windows. The service
is responsible for upstream fetching and normalization; FastMCP
handlers delegate to the service and preserve the existing generic
error boundary. Electricity cost estimation integrates constant power
over complete windows. Thresholds group adjacent qualifying bins;
split blocks are selected greedily without overlap. The battery
model estimates one charge-before-discharge cycle and does not claim
to be a comprehensive operational optimization.

## Additional analytics architecture

Descriptive statistics, price trend and volatility calculations reside
in `optimization.py`, using validated, chronological public intervals.
The negative-price tool delegates to the existing threshold grouping
logic. Day comparison reuses the same statistical helper on two
independent upstream day requests. Population standard deviation and
linear interpolation for quartiles are documented API semantics;
adjacent-change metrics never bridge missing intervals.

## Shared analytics contracts

The service fetches public upstream price data, normalizes it using
`price_schemas.py`, and delegates pure computations to `optimization.py`.
The common validated series checks chronological intervals, local-day
boundaries, resolution lengths and overlaps. Price statistics, volatility,
trends, threshold grouping, contiguous windows and split-block selection
reuse that representation. Day comparison requests two dates independently.

The split-block algorithm is greedy rather than globally optimal for
general scheduling constraints. The battery estimate models only one
idealized charge-before-discharge cycle. Neither tool guarantees actual
bill savings or accounts for a household consumption profile.

## Authenticated linked-device counts

Three privacy-safe service methods delegate to existing read-only
`python-frank-energie` endpoints for batteries, PV systems and vehicles.
They enforce configured credentials before opening a managed upstream
session, validate the expected typed collection field and return only
a count. The MCP boundary maps exceptions to a generic client-facing
error. Device identifiers and detailed configuration are deliberately
excluded. Write-capable upstream methods remain unexposed.

## Authenticated enrollment and contract resolution reads

The account-status tools delegate directly to
`python-frank-energie.user_smart_feed_in()` and
`contract_price_resolution_state(connection_id)`. The service checks
configured credentials and allowlists only stable, non-identifying
boolean/status fields. Raw upstream models, connection identifiers and
personal data are excluded from MCP output. Contract resolution changes
remain intentionally unavailable as MCP tools.

## Aggregated invoice and PV read paths

Annual invoice statistics reuse the upstream `invoices(site_reference)`
model, filtering by local invoice start year and reducing to count,
sum and arithmetic mean. The service never serializes raw invoice
objects. The PV summary tool delegates to
`smart_pv_system_summary(device_id)` and allowlists only status and
numeric totals. Both require credentials and return no identifying
account or device metadata. These tools are read-only.

## Battery detail read path

The battery status tool delegates to upstream
`smart_battery_details(device_id)` and extracts only a validated
state-of-charge percentage, status, last-update timestamp and
capacity. Device identifiers, trading configuration and raw
upstream models are never returned. Credentials are required,
and no upstream mutation is exposed.

## Smart HVAC status boundary

The service delegates to upstream `smart_hvac_status()` in an
authenticated managed session. It allowlists two nullable boolean
flags and a derived availability flag. User IDs, registration
timestamps and the raw upstream object are excluded. The MCP server
does not expose smart HVAC setting mutations.

## Daily consumption aggregation

The read-only consumption tool delegates to upstream
`meter_readings(site_reference)` and selects an inclusive
calendar-date range. It validates dates, finite nonnegative kWh
values and uniqueness of daily records before computing total and
average per observed day. Raw readings and upstream account metadata
never cross the MCP boundary. Credentials and a site reference are
required; missing days are not fabricated as zero consumption.

## Battery session aggregation

The session statistics tool delegates to upstream
`smart_battery_sessions(device_id, start_date, end_date)`.
It aggregates only finite numeric per-session results, counting
all sessions separately from those with reported results.
Raw sessions, device IDs and trading metadata are not serialized
into the MCP response. Date range and authentication are validated;
no battery configuration is modified.

## Billing-period usage and costs boundary

The period totals tool delegates to upstream
`period_usage_and_costs(site_reference, start_date)` and
allowlists three energy categories with their units, usage totals
and cost totals. It does not reimplement upstream billing
calculations, and does not serialize raw usage items, period IDs
or customer identifiers. Credentials and a site reference are
required. The operation is read-only.

## EV charger statistics boundary

The EV charger tool delegates to upstream
`enode_chargers(site_reference, start_date)` and counts
validated charger capability flags. It does not serialize
charger identifiers, intervention details or charging settings,
and does not invoke upstream charging mutations. Credentials
and a site reference are required.

## Monthly cost insights boundary

The monthly insights tool delegates to upstream
`month_insights(site_reference, month)` with a validated
calendar month. It exposes only expected/actual cost totals,
preserving nullable values and rejecting nonfinite amounts.
It does not serialize invoice IDs, account identifiers or
meter-reading timestamps and performs no mutations.

## Account country boundary

The account country tool uses upstream `user_country()` and
allowlists only a validated two-letter country code. It does
not expose the upstream Me payload, user ID or email. It
requires credentials but not a site reference and performs
no mutations.

## Smart battery fleet aggregation

The battery fleet tool delegates to upstream `smart_batteries()`
and aggregates only validated numeric capacity and rated power.
It does not expose device identifiers, settings or brands, and
does not infer unreported capacity. It requires credentials
and performs no mutations.

## Electric vehicle fleet aggregation

The electric vehicle statistics tool delegates to upstream
`enode_vehicles()` and counts validated reachability and
smart charging flags. Vehicle IDs and configuration are
not serialized. Credentials are required; the operation
does not change charging settings.

## Smart PV fleet aggregation

The PV fleet tool delegates to upstream `smart_pv_systems()`
and aggregates validated panel-group counts and declared
capacity. Missing numeric fields are not imputed. It
does not serialize connection EANs, inverter serial numbers
or device identifiers. It requires credentials and is
read-only.

## Current month summary boundary

The current month summary tool delegates to upstream
`month_summary(site_reference)` and allowlists numeric
cost and completeness fields plus the gas-exclusion flag.
It excludes account IDs and meter-reading dates. It does
not duplicate the upstream billing calculations or make
changes to the account. Upstream schema support is required.

## Authentication and privacy

Public market-price tools work without configured credentials. Account/site operations require `FRANK_ENERGIE_USERNAME` and `FRANK_ENERGIE_PASSWORD`; account operations also require `FRANK_ENERGIE_SITE_REFERENCE`. The bridge reads these from the process environment. Credentials are not passed as MCP tool arguments.

The account tool does not expose account details, and the site tool returns only a count. Error messages sent to clients are generic; the server logs exception class names rather than upstream messages. Do not put production credentials or customer data in tests or logs.

## Transports and deployment boundary

The default runtime is stdio. Optional Streamable HTTP binds only to `127.0.0.1` and uses a configurable port (1–65535, default 8000); other hosts and transports are rejected by `main()`. The application does not provide inbound HTTP authentication. Loopback binding is not a substitute for authenticated external access. Public deployment requires a separately designed and verified secure ingress and client authorization.

## Design rules

1. Keep Frank Energie API access and domain/business logic in `python-frank-energie`.
2. Preserve async session cleanup on success and failure.
3. Do not return raw upstream objects, credentials, addresses, or account identifiers from MCP handlers.
4. Keep price response schemas explicit and bounded, and validate timezones and numeric amounts.
5. Add regression tests for protocol contracts, failure paths, and privacy boundaries.
6. Update `MCP_SPEC.md` and this document whenever implemented behavior changes.

## Current limitations and future work

- `get_lowest_price` and `get_highest_price` select minimum and maximum normalized total-price intervals using the shared coverage validation.
- `get_average_prices` calculates the arithmetic mean of normalized `total` values over all returned intervals; it reports missing coverage and does not impute missing prices.
- The minimal `get_account` response indicates success only; it is not an account summary.
- Site discovery returns a count, not selectable site details.
- No persistent login/token lifecycle is implemented in this MCP layer.
- The 200-interval cap is a defensive MCP bound; live upstream response behavior still needs verification.
- Synthetic DST boundary regression tests cover both supported resolutions; real MCP client interoperability remains outstanding.
- External HTTP access must not be enabled without verified authentication and authorization.
- Future additions may include richer privacy-safe account summaries, dynamic resources, and price comparisons, without duplicating upstream business logic.

## Non-goals

- Direct Home Assistant entity support or replication of the Home Assistant integration.
- New GraphQL endpoints or direct API calls from the MCP layer.
- Hidden background synchronization unrelated to MCP requests.

## Battery trading result boundary

The trading result tool reuses the upstream battery summary's
`total_result` without recomputing session-level business logic. It
exposes no account or device identifiers and performs no mutations.
