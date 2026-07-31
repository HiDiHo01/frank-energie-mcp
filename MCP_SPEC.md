# MCP Specification

## Overview

This document defines the intended MCP surface for `frank-energie-mcp`.

The server should expose Frank Energie data through MCP tools, resources, and prompts while delegating all Frank Energie domain access to `python-frank-energie`.

## Principles

- Keep the surface small and predictable.
- Keep tool outputs structured and deterministic.
- Prefer read-only operations for the first release.
- Avoid duplicating backend logic in the MCP server.
- Return data that is easy for LLMs to summarize and compare.
- Build the server on the official Python MCP SDK using a FastMCP-style runtime.

## Tool categories

### Price tools

- `get_current_prices`
- `get_today_prices`
- `get_tomorrow_prices`
- `get_gas_price`

These tools should return normalized price records with timestamps, price values, and contextual metadata.

### Account tools

- `get_account`
- `list_sites`

These tools should return compact account and site summaries.

### Analysis tools

Future tools may include:

- `get_cheapest_hours`
- `get_price_average`
- `estimate_costs`
- `compare_days`
- `suggest_best_schedule`

## Resource categories

Resources should expose structured, read-only data. Good candidates are:

- current price series
- today price series
- tomorrow price series
- gas price series
- account summary
- site metadata

Resources should be compact and stable enough for retrieval without side effects.

## Prompt categories

Prompts should help clients ask useful questions about the data.

Possible prompts:

- summarize today's electricity prices
- compare today and tomorrow
- identify the cheapest charging window
- explain current energy cost trends
- generate a short consumer-friendly summary

## Input validation

Every tool must validate input at the MCP boundary before calling the library layer. Validation should fail fast with clear error messages.

## Output shape

Tool outputs should follow a consistent shape, for example:

```json
{
  "status": "ok",
  "source": "python-frank-energie",
  "data": {}
}
```

Errors should be explicit, structured, and suitable for display in MCP clients.

## Authentication

The MCP server should not invent its own Frank Energie authentication protocol. It should use the existing authentication capabilities of `python-frank-energie`.

## Error handling

The server should translate library exceptions into MCP-friendly errors without leaking secrets or internal stack details by default.

## Versioning

The MCP surface may evolve independently of the library, but breaking changes should be minimized and documented.

## Non-goals

- Direct GraphQL access from the MCP layer
- Home Assistant entity exposure
- Hidden polling loops unrelated to a request
- Duplicate cache implementations unless required by MCP transport behavior
