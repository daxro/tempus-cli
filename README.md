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

The CLI stores the Tempus Home API session locally and persists replacement JWTs returned by supported authenticated reads. The current JWT lifetime is 60 minutes: active use can rotate a JWT, but an expired JWT cannot refresh itself. Run `tempus status` before unattended use. If it reports an expired session, run setup again and approve a new Freja eID+ request.

### Keep an unattended session active

On a machine that stays awake and online, cron can run `status` often enough to rotate the JWT before it expires. Find the absolute executable path with `command -v tempus`, then add this entry with `crontab -e`, replacing the example path:

```cron
*/55 * * * * /absolute/path/to/tempus status --json >/dev/null 2>&1
```

This cron expression runs at minutes 0 and 55, so the maximum gap is 55 minutes. Cron does not catch up missed runs: if the machine sleeps, is offline, or the command fails long enough for the JWT to expire, run setup again and approve Freja eID+.

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
tempus report-absence --child CHILD_NAME --from YYYY-MM-DD --json --no-input
tempus report-absence --child CHILD_NAME --from YYYY-MM-DD --apply --confirm --json --no-input
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

`pickup` lists contacts and reads or previews date assignments. Use `tempus pickup --date YYYY-MM-DD --child CHILD_NAME --json --no-input` to read a date, and add `--id PICKUP_ID` or `--name "Pickup Person"` to preview a change. The preview shows the child, date, current contact, proposed contact, and a `preview_token`. To save that reviewed change, repeat the command with `--apply --confirm --preview-token TOKEN`. Changes to the schedule, contact, or editability invalidate the token. The CLI preserves schedule times, enrollments, message, and alone flags, and reads the saved values back before reporting success. Tempus regenerates internal schedule time IDs. An existing assignment can be replaced; an already assigned contact sends no POST.

Pickup attempts are serialized and recorded privately beside the session in `pickup-writes.json`. An uncertain save is never blindly retried, including after restart. Re-run the approved apply to reconcile by reading; a mismatching unresolved attempt blocks further saves. Contact creation, editing, and removal are unsupported, and the legacy web/GWT backend has been removed. See [pickup verification and limitations](docs/pickup-write-verification.md).

`report-absence` previews a full-day absence for one child. Add `--to YYYY-MM-DD` for an inclusive range. Saving requires both `--apply` and `--confirm`; the CLI checks for existing reports and reads the saved report back.

`upcoming-events` lists upcoming overview events by child and unit. It is read-only and intentionally does not store snapshots, detect changes, or track notification state. Its stable JSON rows contain `child`, `unit`, `id`, `message`, `description`, `start_date`, `stop_date`, and `scheduling_allowed`.

## Safety

- Remote writes are limited to explicitly confirmed date-specific pickup assignments and full-day absence reports. Pickup previews do not write.
- Home API hosts, paths, query keys, response types, and response sizes are checked centrally. Unknown paths and other writes are blocked.
- Session files, cookies, SAML values, query values, and token-like values must never be committed or shared.
- Network access is restricted to HTTPS and an explicit host/path allowlist.

## Sanitized Pickup Fixtures

The Home API pickup request is derived from the official app's payload construction, with generated placeholder fixtures and recorded [source provenance](docs/pickup-write-verification.md). Keep captures and replacement maps outside the repository. Review fixtures before committing: no personal names, phone numbers, personal numbers, cookies, JWTs, SAML values, or sensitive URLs. Source-derived fixtures and live captures must be clearly distinguished.

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
