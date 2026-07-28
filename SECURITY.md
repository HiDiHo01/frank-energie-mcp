# Security Policy

## Supported versions

Security updates apply to the latest active version of the repository and any published release that is still maintained.

## Reporting a vulnerability

Do not report security vulnerabilities in public issues.

Use a private security disclosure channel if available, or contact the maintainer directly through a private channel.

Include as much detail as possible, including:

- affected version
- impact
- reproduction steps
- relevant logs or screenshots, with secrets removed
- suggested mitigation if known

## Sensitive data handling

Never commit or paste the following into issues, pull requests, or prompts:

- API keys
- access tokens
- refresh tokens
- passwords
- personal account data
- customer energy data
- private identifiers

Use sanitized examples only.

## Dependency security

Dependencies should be reviewed before introduction. Prefer minimal, well-maintained packages with a clear purpose.

## Configuration security

Configuration should fail safe. Sensitive values must be handled through environment variables, secret managers, or user-controlled secure storage where appropriate.

## Response handling

The MCP server should avoid returning secrets, private headers, or internal debugging details in normal responses.

## Code review security checks

Before merging security-sensitive changes, verify:

- no secret leakage
- no accidental logging of credentials
- no unsafe file access
- no command injection risk
- no unvalidated external input flows
- no direct duplication of backend authentication logic
