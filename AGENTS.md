# Project Overview

`tempus-cli` is an unofficial, read-only Python CLI for Tempus Home. It uses Freja eID+ through Stockholms stad and stores opted-in local configuration outside the repository.

## Setup And Checks

```bash
uv sync --locked
uv run pytest -q
uv run python -m compileall -q tempus_cli tests
uv build
git diff --check
```

Run the focused tests for changed behavior before the full suite.

## Safety Rules

- Preserve the central HTTPS host/path allowlist and read-only RPC allowlist.
- Do not add remote write operations without an explicitly verified RPC and an explicit user request.
- Never commit or log real personal numbers, cookies, sessions, SAML values, tokens, or unredacted sensitive URLs.
- Use generated placeholder values in tests instead of plausible personal identifiers.
- Keep prompts TTY-only. Non-interactive commands must fail with actionable stderr and no traceback.
- Keep stdout for command data and stderr for prompts, progress, and errors.
- Keep JSON output stable and covered by tests.

## Command Interface

Working commands are `status`, `setup`, `schemas`, `providers`, and `login`.

- Human-readable output is the default.
- Read commands support `--json`.
- `TEMPUS_PERSONNUMMER` is the only supported personal-number environment variable.
- `--no-input` must disable all prompting.

## Documentation

Keep `README.md` concise and human-focused. Keep agent operating instructions in `.agents/skills/tempus-cli/SKILL.md`. Do not add vendor-specific agent instruction files.
