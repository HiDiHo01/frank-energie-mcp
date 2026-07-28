# AI Policy

## Purpose

This repository contains the MCP server for Frank Energie. The server is a separate layer above `python-frank-energie` and must remain lightweight, deterministic, and easy to audit. AI may assist development, but all changes require human review.

## Allowed use of AI

AI may be used to:

- draft or refactor MCP tools, resources, prompts, and documentation
- generate or improve tests
- explain architecture, protocols, and edge cases
- improve validation, typing, logging, and error handling
- assist with issue triage and pull request reviews

## Prohibited use

Do not use AI to:

- invent Frank Energie API behavior or MCP protocol behavior
- bypass tests, reviews, or CI checks
- expose secrets, tokens, personal data, or customer data
- add undocumented behavior, hidden logic, or speculative fallbacks
- duplicate backend logic that already belongs in `python-frank-energie`

## Design requirements for AI-assisted changes

AI-generated code should:

- keep `python-frank-energie` as the only Frank Energie data layer
- avoid direct GraphQL or API reimplementation in the MCP server
- use modern Python with complete type hints
- prefer asynchronous patterns where applicable
- use timezone-aware datetimes
- include meaningful docstrings for public modules, classes, and functions
- use lazy `%` logging formatting
- provide descriptive validation and error messages
- avoid dead code, duplicate logic, and unnecessary dependencies

## Review requirements

Every AI-assisted pull request must be reviewed by a human contributor who understands the code. The reviewer must verify that:

- the change matches the MCP design
- the change is correct and test-covered
- no sensitive data was introduced
- the change does not duplicate or drift from the shared library

## Privacy and security

Never place production credentials, authentication tokens, or personal energy-account data into prompts, issues, commits, or pull requests. Use sanitized example data only.

## Maintenance

This policy should be updated when the repository scope, protocol support, or dependency structure changes.
