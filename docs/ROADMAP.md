# Roadmap

## Phase 1: Foundation

- create the MCP server package structure
- connect to `python-frank-energie`
- expose the first read-only tools
- add basic resources and prompts
- document setup and local development

## Phase 2: Core features

- current prices
- today and tomorrow price curves
- gas pricing
- account and site summary tools
- normalized response models
- initial integration tests

## Phase 3: Analysis helpers

- cheapest-hour detection
- average and median price calculations
- cost estimation helpers
- day-to-day comparisons
- concise AI-friendly summaries

## Phase 4: Advanced support

- richer resources for price history
- configuration-driven behavior
- optional caching improvements
- improved error translation
- examples for common assistant workflows

## Phase 5: Hardening

- broader test coverage
- packaging and release automation
- CI quality gates
- security review
- documentation polish

## Non-goals

- direct duplication of Frank Energie API logic
- Home Assistant entity support
- background jobs unrelated to MCP requests
- unstable experimental tools in the initial release
