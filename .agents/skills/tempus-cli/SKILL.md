---
name: tempus-cli
description: Operate the unofficial read-only Tempus Home CLI. Use when checking local Tempus session status, listing public schemas or login providers, or verifying Freja eID+ login.
compatibility: Requires the tempus command, network access to the allowlisted Tempus and Stockholm login hosts, and human Freja eID+ approval for login.
---

# Tempus CLI

## Rules

- Use `--json` for `status`, `schemas`, and `providers`.
- Use `--no-input` whenever the command runs non-interactively.
- Provide the personal number only through the process environment variable `TEMPUS_PERSONNUMMER`.
- Never print, store in the repository, or return personal numbers, cookies, sessions, SAML values, or tokens.
- Freja eID+ login always requires human approval.
- Treat exit code `2` as invalid or missing input, `1` as an operational failure, and `130` as interruption.

## Common Commands

```bash
tempus status --json
tempus schemas --area Stockholm --json
tempus providers --schema-id 399 --json
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus setup --no-input
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus login --no-input
```

Human-readable output is available by omitting `--json`.
