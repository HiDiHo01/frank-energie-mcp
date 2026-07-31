# Architecture

## Overview

Frank Energie MCP is a standalone Model Context Protocol server for Frank Energie.

It is designed as a thin, async-first layer on top of `python-frank-energie`.

```text
MCP client
    │
    ▼
frank-energie-mcp
    │
    ├── FastMCP server runtime
    ├── tool registration
    ├── read-only resources
    └── prompts
    │
    ▼
python-frank-energie
    │
    ▼
Frank Energie GraphQL API
```

## Responsibilities

### frank-energie-mcp

The MCP repository is responsible for:

- MCP transport and tool registration
- resource and prompt exposure
- response shaping for MCP clients
- boundary validation
- lightweight presentation logic

### python-frank-energie

The shared library is responsible for:

- authentication
- GraphQL communication
- API retries and error translation
- caching and polling behavior
- price modelling
- account and site data retrieval
- reusable Frank Energie domain logic

## Design rules

1. Do not reimplement Frank Energie API access in the MCP repository.
2. Do not duplicate price calculation logic in the MCP repository.
3. Keep the server runtime thin and focused on FastMCP registration.
4. Prefer async-first handlers and read-only resources.
5. Keep tools deterministic and stable for MCP clients.

## Suggested internal modules

- `server.py`: FastMCP bootstrap and tool/resource/prompt registration
- `library.py`: bridge to `python-frank-energie`
- `tools/`: callable MCP tool handlers
- `resources/`: read-only structured resources
- `prompts/`: reusable prompt templates
- `models.py`: MCP-facing response models

## Data flow

1. The client sends a tool call to the MCP server.
2. The server validates the input.
3. The server calls the corresponding `python-frank-energie` API through `library.py`.
4. The library performs the Frank Energie request.
5. The server formats the result for the client.

## Initial scope

The first version should expose a small set of stable tools:

- current electricity prices
- today's prices
- tomorrow's prices
- gas price
- account summary
- list of sites

## Future extensions

Later versions can add:

- cost estimation
- cheapest-hour analysis
- schedule recommendations
- price comparison prompts
- history and trend resources
- account-specific summaries

## Non-goals

- Direct Home Assistant entity support
- Duplication of the Home Assistant integration
- New Frank Energie API endpoints outside the library layer
- Hidden background synchronization unrelated to MCP requests
