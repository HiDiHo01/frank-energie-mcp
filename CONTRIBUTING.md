# Contributing

Thank you for helping improve `frank-energie-mcp`.

## Scope

This repository provides a standalone MCP server for Frank Energie. Contributions should keep the project thin, typed, async-first, and aligned with `python-frank-energie`.

## Development expectations

- Use modern Python.
- Keep type hints complete.
- Add docstrings for public modules, classes, and functions.
- Use timezone-aware datetimes.
- Use lazy `%` formatting in logging.
- Keep the MCP server free of duplicated Frank Energie domain logic.
- Write tests for new behavior and bug fixes.

## Suggested workflow

1. Create a feature branch.
2. Make a focused change.
3. Run formatting, linting, and tests.
4. Update documentation if behavior changed.
5. Open a pull request.

## Review expectations

A pull request should explain:

- what changed
- why it changed
- how it was tested
- whether AI assisted with the work

## Architecture rule

All Frank Energie communication must go through `python-frank-energie`. Do not add direct GraphQL calls or duplicate data-fetching logic in this repository.

## Writing style

Prefer:

- clear module boundaries
- descriptive function and variable names
- small, readable functions
- explicit validation and error messages
- small, stable MCP tool outputs

Avoid:

- large monolithic modules
- hidden side effects
- unnecessary abstractions
- speculative features without a concrete use case

## Testing

At minimum, new work should include or update:

- unit tests for pure logic
- async tests for MCP handlers where relevant
- validation tests for user input
- regression tests for bug fixes

## Security

Never include real credentials, tokens, or personal account data in code examples, tests, or pull requests.
