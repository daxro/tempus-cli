# tempus-cli

Read-only CLI for Tempus Hemma. This is a standalone repo, separate from Botsson, deformentor and laget.

## Safety contract

- Phase 1 is read-only. There are no commands that save, update, submit or confirm Tempus data.
- Tempus writes are blocked centrally by the transport guard.
- Login uses Freja eID+ through Stockholms stad.
- Sessions are in-memory by default. Opt-in cookie helpers exist for manual debugging only and refuse files inside this repo.
- Debug/discovery output redacts cookies, SAML fields, query values, personnummer and token-like values.

## Commands

```bash
tempus --help
tempus status
tempus schemas --area Stockholm
tempus schemas --area-id 12
tempus providers --schema-id 399
tempus login
tempus children
tempus pickup --child Viggo --date YYYY-MM-DD
```

`children` and `pickup` are placeholders until the authenticated read-only RPC methods have been discovered. They fail closed and do not guess method names.

## Development

```bash
uv run pytest -q
uv run python -m compileall -q tempus_cli tests
git diff --check
```
