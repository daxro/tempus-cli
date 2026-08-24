# Security Policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/daxro/tempus-cli/security/advisories/new).

Do not include cookies, session files, SAML values, tokens, or unredacted URLs in public issues or reports. Include the `tempus --version` output, the command used, and redacted error output.

Pickup write support must not be enabled from raw production traffic. Use sanitized Home API fixtures that remove personal numbers, child names, cookies, JWTs, SAML values, tokens, and unredacted URLs.

Keep raw HAR or proxy output and replacement maps outside the repository. Before any `POST /schedules` implementation is enabled, reviewed sanitized fixtures must prove the exact request and response, the request must use a separate write allowlist, and tests must cover stale-state checks plus post-write verification. The CLI must not fall back to the legacy web/GWT API.
