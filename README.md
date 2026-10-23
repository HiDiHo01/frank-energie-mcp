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
git switch fix/fastmcp-bootstrap-and-ci
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
| Tool | `get_gas_price` | Returns the current gas interval or `null` when unavailable |
| Tool | `get_account` | Not operational; authentication and site reference are missing |
| Tool | `list_sites` | Delegates to upstream `UserSites()`; authentication required |
| Resource | `frank-energie://capabilities` | Static description of capabilities |
| Prompt | `summarize_energy_prices` | Static instructions for comparing prices |

Price requests use the `Europe/Amsterdam` calendar date. Tool output is not yet guaranteed to follow a stable normalized JSON schema.

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

- Environment-based login and explicit site-reference selection are implemented, but token lifecycle, privacy-safe error mapping and operational validation remain pending.
- Current-interval and gas-only extraction use upstream `current_hour`; complete serialization and integration validation remain pending.
- Upstream response serialization and privacy-safe error handling need verification.
- End-to-end MCP client interoperability has not been validated.

See [ARCHITECTURE.md](ARCHITECTURE.md), [MCP_SPEC.md](MCP_SPEC.md), [AI_POLICY.md](AI_POLICY.md) and [SECURITY.md](SECURITY.md). Do not commit credentials or personal account data.
