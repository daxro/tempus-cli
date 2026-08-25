# tempus-cli

An unofficial CLI for Tempus Home using Freja eID+ through Stockholms stad.

This project is not affiliated with Tempus or Stockholms stad.

## Install

Requires Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/daxro/tempus-cli.git
tempus --help
```

Update an existing install:

```bash
uv tool upgrade tempus-cli
```

Uninstall with `uv tool uninstall tempus-cli`.

## Setup

For agent setup, give your personnummer to the agent and have it run:

```bash
tempus setup --personnummer YYYYMMDDNNNN
```

Approve the Freja eID+ request on your phone. Setup saves local config and session files outside the repository with `0600` permissions. It does not write Tempus data.

The CLI stores the Tempus Home API session locally and persists replacement JWTs returned by supported authenticated reads. These JWTs are short-lived: active use can rotate them, but an expired JWT cannot refresh itself. Run `tempus status` before unattended use. If it reports an expired session, run setup again and approve a new Freja eID+ request.

Interactive setup remains available:

```bash
tempus setup
```

For automation compatibility, `TEMPUS_PERSONNUMMER` remains supported for `--no-input` or non-TTY setup, but `setup --personnummer` is the primary agent-facing path.

## Commands

```bash
tempus status
tempus status --json
tempus schemas --area Stockholm --json
tempus providers --schema-id 399 --json
tempus upcoming-events --json
tempus upcoming-events --child CHILD_NAME --json
tempus upcoming-events --child CHILD_NAME --json --no-input
tempus schedules --from YYYY-MM-DD --to YYYY-MM-DD --json --no-input
tempus attendance --from YYYY-MM-DD --to YYYY-MM-DD --json --no-input
tempus absences --from YYYY-MM-DD --to YYYY-MM-DD --json --no-input
tempus calendar-events --from YYYY-MM-DD --to YYYY-MM-DD --json --no-input
tempus messages --since YYYY-MM-DD --json --no-input
tempus blog-posts --since YYYY-MM-DD --json --no-input
tempus todos --json --no-input
tempus meetings --json --no-input
tempus reviews --json --no-input
tempus calendar-link --json --no-input
tempus pickup --json
tempus pickup --date YYYY-MM-DD --child CHILD_NAME --json
tempus pickup --date YYYY-MM-DD --child CHILD_NAME --name "Example Guardian" --json
tempus login
```

Human-readable output is the default. Read commands support stable JSON for scripts and agents. Date ranges are inclusive and limited to 366 days.

`login` verifies the Freja login flow without saving a session. `status` verifies the persisted Home API JWT with `/init` without printing account data.

`pickup` lists pickup contacts and previews date assignments. To check who picks up a child on a specific date, use `tempus pickup --date YYYY-MM-DD --child CHILD_NAME --json`. To preview assigning an existing contact, add `--id PICKUP_ID` or `--name "Pickup Person"`. Home API writes remain blocked until reviewed sanitized `POST /schedules` fixtures verify the exact request and response; the CLI never falls back to the legacy web/GWT API.

`upcoming-events` lists upcoming overview events by child and unit. It is read-only and intentionally does not store snapshots, detect changes, or track notification state. Its stable JSON rows contain `child`, `unit`, `id`, `message`, `description`, `start_date`, `stop_date`, and `scheduling_allowed`.

## Safety

- Remote Tempus operations are read-only. Pickup previews do not write.
- Home API hosts, paths, query keys, response types, and response sizes are checked centrally. Unknown and write-like paths are blocked.
- Session files, cookies, SAML values, query values, and token-like values must never be committed or shared.
- Network access is restricted to HTTPS and an explicit host/path allowlist.

## Sanitized Pickup Fixtures

Pickup date-assignment payload work must start from a sanitized Home API capture, never raw production traffic. Keep captures and replacement maps outside the repository and replace personal data with generated placeholders before adding a fixture.

```json
{
  "Real child name": "Example Child",
  "Real pickup contact name": "Example Guardian"
}
```

Review every fixture before committing. It must contain generated placeholders only: no personal numbers, real names, cookies, JWTs, SAML values, raw production traffic, or unredacted sensitive URLs. A fixture alone does not enable writes; tests must also prove request construction, the separate write allowlist, stale-state checks, and post-write verification.

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
