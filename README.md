# Frank Energie MCP

Frank Energie MCP is a standalone Model Context Protocol server for Frank Energie. It sits on top of `python-frank-energie` and exposes energy data in a form that MCP clients can consume directly.

## Purpose

The repository exists to provide a reusable AI-facing layer for:

- current electricity prices
- today's and tomorrow's price curves
- gas prices
- account and site information
- future analysis and planning tools

The MCP server does not reimplement Frank Energie API logic. That responsibility stays in `python-frank-energie`.

## Architecture

```text
LLM / MCP client
        │
        ▼
Frank Energie MCP server
        │
        ▼
python-frank-energie
        │
        ▼
Frank Energie API
```

## Repository goals

- Keep the MCP server thin and auditable.
- Reuse the shared Python library for all Frank Energie communication.
- Provide deterministic tool output for LLMs.
- Keep the codebase async-first, typed, and testable.

## Runtime choice

This repository is designed around the official Python MCP SDK and a FastMCP-style server. Tools should remain async, resources should be read-only, and prompts should stay lightweight and deterministic.

## First milestone

The first release should expose these tools:

- `get_current_prices`
- `get_today_prices`
- `get_tomorrow_prices`
- `get_gas_price`
- `get_account`
- `list_sites`

## Planned structure

```text
frank-energie-mcp/
├── src/
│   └── frank_energie_mcp/
│       ├── __init__.py
│       ├── __main__.py
│       ├── server.py
│       ├── auth.py
│       ├── config.py
│       ├── models.py
│       ├── tools/
│       ├── resources/
│       └── prompts/
├── tests/
├── docs/
├── examples/
├── pyproject.toml
├── CONTRIBUTING.md
├── AI_POLICY.md
├── SECURITY.md
├── LICENSE
└── CHANGELOG.md
```

## Scope

The server should provide MCP-native access to Frank Energie data while delegating all domain logic, authentication details, caching, and GraphQL handling to `python-frank-energie`.
