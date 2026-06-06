# Security Policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/daxro/tempus-cli/security/advisories/new).

Do not include cookies, session files, SAML values, tokens, or unredacted URLs in public issues or reports. Include the `tempus --version` output, the command used, and redacted error output.

Pickup write support must not be enabled from raw production traffic. Use sanitized fixtures that remove personal numbers, child names, cookies, sessions, SAML values, tokens, and unredacted URLs.

For pickup date-assignment capture, keep raw HAR or proxy output outside the repository. Use `uv run python -m tempus_cli.pickup_fixtures --input RAW --replacements REPLACEMENTS --output tests/fixtures/pickup_date_assignment/NAME.json`, then review the generated fixture before committing it. The replacement file must also stay outside the repository and map real names to generated placeholders.
