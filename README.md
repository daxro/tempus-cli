# tempus-cli

An unofficial, read-only CLI for Tempus Home using Freja eID+ through Stockholms stad.

This project is not affiliated with Tempus or Stockholms stad.

## Install

Requires Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/daxro/tempus-cli.git
tempus --help
```

Uninstall with `uv tool uninstall tempus-cli`.

## Setup

Interactive setup:

```bash
tempus setup
```

Non-interactive setup:

```bash
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus setup --no-input
```

Setup requires human approval in Freja eID+. It saves local config and session files outside the repository with `0600` permissions. It does not write Tempus data.

## Commands

```bash
tempus status
tempus status --json
tempus schemas --area Stockholm --json
tempus providers --schema-id 399 --json
tempus login
```

Human-readable output is the default. `status`, `schemas`, and `providers` support stable JSON for scripts and agents.

`login` verifies the Freja login flow without saving a session. `status` fails closed when authenticated read verification is unavailable.

## Safety

- Remote Tempus operations are read-only.
- Unknown and write-like Tempus RPC methods are blocked centrally.
- Session files, cookies, SAML values, query values, personal numbers, and token-like values must never be committed or shared.
- Network access is restricted to HTTPS and an explicit host/path allowlist.

## Agents

Agents operating the CLI should read [`.agents/skills/tempus-cli/SKILL.md`](.agents/skills/tempus-cli/SKILL.md).

Agents modifying this repository should read [`AGENTS.md`](AGENTS.md).

## Development

```bash
uv sync --locked
uv run pytest -q
uv run python -m compileall -q tempus_cli tests
uv build
git diff --check
```

## License

[MIT](LICENSE)
