# tempus-cli

An unofficial CLI for Tempus Home using Freja eID+ through Stockholms stad.

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
tempus pickup --json
tempus pickup --child CHILD_NAME --name "Example Guardian" --phone "0700000000" --json
tempus pickup --date YYYY-MM-DD --child CHILD_NAME --name "Example Guardian" --json
tempus login
```

Human-readable output is the default. `status`, `schemas`, `providers`, and `pickup` support stable JSON for scripts and agents.

`login` verifies the Freja login flow without saving a session. `status` verifies a persisted session with an authenticated pickup read without printing pickup data.

`pickup` lists pickup contacts and previews guarded pickup contact changes. It also previews date-specific pickup assignment with `--date YYYY-MM-DD --child CHILD_NAME --id PICKUP_ID` or `--date YYYY-MM-DD --child CHILD_NAME --name "Pickup Person"`. Preview is the default. Existing-contact date assignment can be applied with `--apply --confirm` after stale-state checks and post-write verification. Contact create, update, and remove remain disabled until sanitized Tempus write fixtures verify the exact GWT payloads.

## Safety

- Remote Tempus operations are read-only except explicitly confirmed pickup writes after fixture-backed enablement.
- Unknown and write-like Tempus RPC methods are blocked centrally; pickup writes use a separate allowlist.
- Session files, cookies, SAML values, query values, personal numbers, and token-like values must never be committed or shared.
- Network access is restricted to HTTPS and an explicit host/path allowlist.

## Sanitized Pickup Fixtures

Pickup date-assignment payload work must start from a sanitized capture, never raw production traffic. Save the browser or proxy capture outside the repository, then create a local replacement file outside the repository:

```json
{
  "Real child name": "Example Child",
  "Real pickup contact name": "Example Guardian"
}
```

Generate the fixture with:

```bash
uv run python -m tempus_cli.pickup_fixtures --input /path/outside/repo/raw.har --replacements /path/outside/repo/replacements.json --output tests/fixtures/pickup_date_assignment/assignment.har.json
```

Review the output before committing. It must contain generated placeholders only, no personal numbers, real names, cookies, sessions, SAML values, tokens, raw production traffic, or unredacted sensitive URLs. This sanitizer does not enable writes; date-assignment writes remain disabled until reviewed sanitized fixtures prove the exact GWT payloads.

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
