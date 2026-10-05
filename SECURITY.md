# Security Policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/daxro/tempus-cli/security/advisories/new).

Do not include cookies, session files, SAML values, tokens, or unredacted URLs in public issues or reports. Include the `tempus --version` output, the command used, and redacted error output.

Pickup write support must not be enabled from raw production traffic. Use sanitized Home API fixtures that remove personal numbers, child names, cookies, JWTs, SAML values, tokens, and unredacted URLs.

Keep raw HAR or proxy output and replacement maps outside the repository. Pickup request construction must be backed by reviewed app-code evidence or a sanitized capture and generated fixtures. The separate pickup write allowlist permits only a single child/date `POST /schedules`. A durable private attempt record prevents repeated writes after uncertain outcomes; post-write verification compares every editable schedule value, excluding the observed server-generated `scheduleTimeId`. Full raw state participates in stale-preview checks. The HTTP response alone is not proof of success. The legacy web/GWT backend has been removed. Login form traffic uses its own HTTPS host/path and field allowlists.
