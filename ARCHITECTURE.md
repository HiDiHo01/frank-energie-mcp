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
- `The minimal `get_account` response indicates success only; it is not an account summary.
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
