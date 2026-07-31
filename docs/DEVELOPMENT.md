# Development

## Requirements

- Python 3.14 or newer
- a working checkout of `python-frank-energie`
- the official Python MCP SDK using a FastMCP-style runtime
- a modern async-friendly development environment

## Goals

Development in this repository should be:

- typed
- async-first
- test-covered
- easy to review
- aligned with the shared Frank Energie library
- aligned with the official MCP SDK and its FastMCP-style server model

## Local workflow

1. Create or activate a virtual environment.
2. Install the project in editable mode.
3. Install development dependencies.
4. Run formatting, linting, and tests.
5. Make focused commits.

## Style expectations

Use:

- complete type hints
- docstrings for public modules, classes, and functions
- timezone-aware datetimes
- `snake_case` names
- lazy `%` logging formatting
- clear validation messages
- small, reusable helper functions

Avoid:

- large, mixed-responsibility modules
- direct duplicate Frank Energie API logic
- blocking I/O in async code
- ambiguous or hidden control flow
- unnecessary imports

## MCP implementation guidance

When adding tools, resources, or prompts:

- keep outputs compact and structured
- validate inputs before calling the library
- return deterministic payloads where possible
- translate backend errors into user-friendly MCP errors
- avoid leaking internal stack traces or secrets
- keep `server.py` thin and focused on MCP registration
- keep domain logic in `library.py` and `python-frank-energie`

## Testing guidance

Add tests for:

- successful tool calls
- invalid input handling
- backend error translation
- serialization and response shape
- regression cases for prior bugs

Prefer separate tests for the MCP boundary and for pure helper logic.

## Dependency boundary

The MCP repository should remain a thin layer on top of `python-frank-energie`. If a feature requires domain knowledge, price calculation, or API handling, it belongs in the shared library unless it is strictly MCP formatting.

## Release discipline

Before release:

- run the full test suite
- check formatting and linting
- review dependency changes
- verify tool names and response shapes
- update documentation when the public surface changes
