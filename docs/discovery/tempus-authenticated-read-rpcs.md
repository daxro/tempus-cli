# Tempus authenticated read RPC discovery

## Rules

- No cookies, tokens, SAML values, personal identifiers, or full child/person data.
- Record only method name, endpoint path, payload shape, response shape, and read/write assessment.
- Do not record raw request or response bodies.

## Login/session

- Date: 2026-06-04
- Login route: Stockholm -> Freja eID+ -> Tempus Home
- Session source: none available in repo/CLI at implementation time
- Status result: fail-closed until authenticated read RPC exists

## Observed RPCs

No authenticated child/schedule/pickup RPC has been observed yet.

Public pre-login RPCs already verified elsewhere:

### RPC 1

- Method: `getSchemas`
- Endpoint path: `/tempusHome/tempusHome/service`
- Direction: read-only
- Trigger in UI: selecting area / loading schemas
- Request shape: GWT RPC with area id
- Response shape: schema names and ids
- Why it is considered read-only: public lookup, no authenticated child data, no save control used
- Safe to allowlist: yes

### RPC 2

- Method: `getGrandIdIdentityProviders`
- Endpoint path: `/tempusHome/tempusHome/service`
- Direction: read-only
- Trigger in UI: selecting verksamhet/login provider
- Request shape: GWT RPC with schema id
- Response shape: provider names/options
- Why it is considered read-only: public login-provider lookup, no save control used
- Safe to allowlist: yes

## Candidate pickup data

- Child model fields: public client contains `HomeChild` model type; authenticated response shape not verified
- Schedule/day fields: public client contains `ChildScheduleHomeWrapper` and `DaySchedule` model types; authenticated response shape not verified
- Pickup fields: public client contains `Pickup` and `PickupSettings` model types; authenticated response shape not verified
- Date field format: not verified for authenticated pickup RPC
- Empty pickup representation: not verified
- Locked/non-editable representation: not verified

## Blocker

- 2026-06-04: Freja eID+ approval reached `APPROVED`, but the follow-up Tempus Home request timed out while discovering the GWT permutation.
- A retry fetching `https://home.tempusinfo.se/tempusHome/tempusHome/tempusHome.nocache.js` also timed out before any authenticated child/schedule/pickup RPC could be observed.
- A real authenticated Tempus session and a responding Tempus Home server are required to observe the read-only RPC for Viggo's schedule/pickup.
- No guessed RPC method or payload has been allowlisted.
