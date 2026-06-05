---
name: tempus-cli
description: Operate the unofficial Tempus Home CLI. Use when checking local Tempus session status, listing public schemas, login providers, or pickup contacts, or verifying Freja eID+ login.
compatibility: Requires the tempus command, network access to the allowlisted Tempus and Stockholm login hosts, and human Freja eID+ approval for login.
---

# Tempus CLI

## Rules

- Use `--json` for `status`, `schemas`, `providers`, and `pickup`.
- Use `--no-input` whenever the command runs non-interactively.
- Provide the personal number only through the process environment variable `TEMPUS_PERSONNUMMER`.
- Never print, store in the repository, or return personal numbers, cookies, sessions, SAML values, or tokens.
- Freja eID+ login always requires human approval.
- Treat `tempus pickup` as read/preview-only unless the command itself supports fixture-backed `--apply --confirm` writes.
- Treat exit code `2` as invalid or missing input, `1` as an operational failure, and `130` as interruption.

## Common Commands

```bash
tempus status --json
tempus schemas --area Stockholm --json
tempus providers --schema-id 399 --json
tempus pickup --json
tempus pickup --date YYYY-MM-DD --child CHILD_NAME --id PICKUP_ID --json
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus setup --no-input
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus login --no-input
```

Human-readable output is available by omitting `--json`.
