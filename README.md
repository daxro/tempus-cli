# tempus-cli

Read-only CLI for Tempus Hemma. This is a standalone repo, separate from Botsson, deformentor and laget.

## Safety contract

- Phase 1 is read-only. There are no commands that save, update, submit or confirm Tempus data.
- Tempus writes are blocked centrally by the transport guard.
- Login uses Freja eID+ through Stockholms stad.
- `login` keeps sessions in-memory by default. `setup` explicitly saves config and session outside the repo.
- Debug/discovery output redacts cookies, SAML fields, query values, personnummer and token-like values.

## Commands

```bash
tempus --help
tempus setup
tempus setup --no-input
tempus status
tempus status --json
tempus schemas --area Stockholm
tempus schemas --area-id 12
tempus providers --schema-id 399
tempus login
tempus children
tempus pickup --child Viggo --date YYYY-MM-DD
```

`children` and `pickup` are placeholders until the authenticated read-only RPC methods have been discovered. They fail closed and do not guess method names.

## Setup

Interactive setup:

```bash
tempus setup
```

Non-interactive setup, same shape as deformentor:

```bash
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus setup --no-input
```

`PERSONNUMMER` is also accepted for compatibility. Setup uses the personnummer-based Freja flow through Stockholm, asks you to approve in Freja eID+, then saves config and session outside the repo with `0600` file permissions. The normal `tempus login` command still verifies login without saving a session.

## Status

Human-readable:

```bash
tempus status
```

Machine-readable:

```bash
tempus status --json
```

Status reports whether config exists, whether a persisted session exists, and whether authenticated read verification is available. Authenticated child/pickup reads still remain disabled until the read RPCs are discovered.

## Examples

```bash
tempus schemas --area Stockholm
tempus providers --schema-id 399
tempus pickup --child Viggo --date 2026-06-08
```

Pickup is read/preview only. Tempus writes are disabled until a verified write RPC exists.

## Exit codes

- `0`: success
- `1`: runtime, network, login, or discovery error
- `2`: invalid input or usage error

## Development

```bash
uv run pytest -q
uv run python -m compileall -q tempus_cli tests
git diff --check
```
