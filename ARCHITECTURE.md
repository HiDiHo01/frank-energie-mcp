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
| `server.py` | FastMCP creation, six tool registrations, resource, prompt, safe tool error handling, transport configuration, and minimal account/site responses |
| `library.py` | `FrankEnergieService`, typed upstream protocol, managed `FrankEnergieLibraryBridge`, environment configuration, and active-interval selection |
| `price_schemas.py` | Strict Pydantic price models, explicit field whitelisting, timestamp/amount validation, JSON normalization, and array bounds |
| `tools/__init__.py` | Legacy package retained for import compatibility; tool implementations now live in `server.py` |
| `models.py` | Legacy generic dataclasses; not the active price response contract |

Separate `auth.py`, `config.py`, `resources/`, and `prompts/` implementations are not part of the current runtime architecture. Authentication and configuration are in `library.py`; the resource and prompt are registered in `server.py`.

## Responsibilities and boundaries

### MCP layer

- Expose six asynchronous read-only tools, one static resource, and one static prompt.
- Validate `resolution` as `PT15M` or `PT60M` at the tool boundary.
- Use `Europe/Amsterdam` dates for today/tomorrow price requests.
- Select upstream `current_hour` records for current electricity/gas prices.
- Normalize market prices to explicitly permitted public fields; do not serialize raw upstream models.
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

Price interval normalization requires ordered timezone-aware timestamps, finite numeric totals, and no more than 200 intervals per energy type for full-day results. This bound is currently implementation-defined rather than verified against every upstream resolution or future API shape.

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

- The minimal `get_account` response indicates success only; it is not an account summary.
- Site discovery returns a count, not selectable site details.
- No persistent login/token lifecycle is implemented in this MCP layer.
- The 200-interval limit and upstream resolution behavior need contract verification.
- A real MCP client interoperability test and DST boundary tests are still outstanding.
- External HTTP access must not be enabled without verified authentication and authorization.
- Future additions may include richer privacy-safe account summaries, dynamic resources, and price comparisons, without duplicating upstream business logic.

## Non-goals

- Direct Home Assistant entity support or replication of the Home Assistant integration.
- New GraphQL endpoints or direct API calls from the MCP layer.
- Hidden background synchronization unrelated to MCP requests.
