---
name: tempus-cli
description: Operate the unofficial Tempus Home CLI. Use for session status, public login discovery, schedules, attendance, absences, calendar events, messages, blog posts, action items, meetings, reviews, calendar-link status, pickup reads/previews, or Freja eID+ login.
compatibility: Requires the tempus command, network access to the allowlisted Tempus and Stockholm login hosts, and human Freja eID+ approval for login.
---

# Tempus CLI

## Rules

- Use `--json` for stable machine-readable output from all read commands.
- Use `--no-input` whenever the command runs non-interactively.
- For "who picks up", "who is picking up", or pickup-by-date questions, use `tempus pickup --date YYYY-MM-DD --child CHILD_NAME --json --no-input`. Do not use `tempus pickup --child CHILD_NAME` for date questions; that only filters pickup contacts.
- If setup is missing, ask the user for personnummer, then run `tempus setup --personnummer VALUE`.
- Tell the user to approve the Freja eID+ request on their phone.
- Never print, store in the repository, or return cookies, sessions, SAML values, or tokens.
- Freja eID+ login always requires human approval.
- Home API JWTs are short-lived. Supported authenticated reads rotate and save replacement JWTs during active use, but an expired JWT cannot refresh itself. Check `tempus status --json` before live reads; if the session is expired, run setup again and tell the user to approve Freja eID+.
- Treat `tempus pickup` as read/preview-only. Home API writes are blocked pending reviewed sanitized fixtures; never use the legacy GWT API as a fallback.
- Treat `tempus upcoming-events` as read-only. It does not store snapshots, detect changes, or manage notification state.
- Treat exit code `2` as invalid or missing input, `1` as an operational failure, and `130` as interruption.
- For pickup date-assignment research, keep raw captures and replacement maps outside the repository. Commit only reviewed Home API fixtures containing generated placeholders.

## Common Commands

```bash
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
tempus pickup --date YYYY-MM-DD --child CHILD_NAME --id PICKUP_ID --json
tempus setup --personnummer YYYYMMDDNNNN
TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus login --no-input
```

Human-readable output is available by omitting `--json`.

## Update

Update the installed CLI with:

```bash
uv tool upgrade tempus-cli
```
