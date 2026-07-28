# Architecture

## Overview

Frank Energie MCP is a standalone Model Context Protocol server that exposes Frank Energie data to MCP clients.

The repository is intentionally thin. It delegates all Frank Energie-specific communication and domain logic to `python-frank-energie`.

```text
MCP client
    │
    ▼
frank-energie-mcp
    │
    ▼
python-frank-energie
    │
    ▼
Frank Energie API
```

## Responsibilities

### frank-energie-mcp

The MCP server is responsible for:

- MCP transport and protocol handling
- tool registration
- resource registration
- prompt registration
- response shaping for LLMs
- lightweight presentation logic
- validation at the MCP boundary

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
3. Do not let the MCP layer own business rules that belong in the shared library.
4. Keep MCP responses deterministic and compact.
5. Prefer async boundaries end to end.

## Suggested internal modules

- `server.py`: MCP server bootstrap and registration
- `auth.py`: bridge to `python-frank-energie` authentication
- `config.py`: environment and runtime configuration
- `models.py`: MCP-facing response models
- `tools/`: callable MCP tools
- `resources/`: read-only structured resources
- `prompts/`: reusable prompt templates

## Data flow

1. The client sends a tool call to the MCP server.
2. The MCP server validates the input.
3. The server calls the corresponding `python-frank-energie` API.
4. The library performs the Frank Energie request.
5. The MCP server formats the result for the client.

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
