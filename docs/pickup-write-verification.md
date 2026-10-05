# Pickup request evidence and verification

The request is reconstructed from Tempus Hemma **3.43.4**, package `se.tempusinfo.tempushemma2`, version code 24478. The app APK was downloaded for static inspection from `https://d.apkpure.net/b/APK/se.tempusinfo.tempushemma2?version=latest`; it was not installed or executed. The official package identity is listed on [Google Play](https://play.google.com/store/apps/details?id=se.tempusinfo.tempushemma2). The download is a third-party mirror, not a Play download; the publisher signing certificate was not independently verified against Play.

APK SHA-256: `9f266c805e844077d2d203b9f881356044dabcc7ac23d35782b787eed4b3cb99`. Raw APK, bundle, disassembly, and manifests remain outside the checkout. Hermes bytecode v98 is marked recent/unsupported by the disassembler; evidence comes from manually tracing these small, explicit instructions rather than trusting reconstructed application-wide control flow.

- Module function 1987 sets `schedulesBaseUrl` to `/schedules`.
- Function 10317 connects `postSchedules` to query function 20161. Function 20161 returns the URL, `HttpMethod.POST`, and its argument unchanged as the body. There are no version/precondition headers in this mutation.
- Function 10318 `createPayload(childId, dates, times, extraInformation)` returns `{childId, schedules}`. Each schedule has `date`, `scheduleTimes`, `message`, `pickupId`, `arrivingAlone`, and `departingAlone`. Each time has `startTime`, `stopTime`, and `enrollmentId`. `scheduleTimeId` is server metadata and is not sent by this constructor. Callers 28069/28595 and 28635/28727 map selections to these child records, producing a list.
- Function 10618 `cleanStopTime` clamps stop times to 1439 minutes. The CLI refuses values that would need clamping, to preserve existing times.
- Functions 10944/10945 apply calendar-event `locked`, `scheduleFreezeDate`, `interval`, and `freezeOnlyOnLeave` rules. Functions 10319/20163 apply the department's `lateScheduleLockedDays` when it is positive and the date distance is less than that value.

`tests/fixtures/home_api/pickup_write.json` uses generated placeholders to exercise this request. It is **source-derived**, not a captured production request or a live-success response. Tests cover actual request construction, the pickup-only write path, preservation, stale previews, freezes/locks, verification failure, concurrency, and durable uncertainty recovery.

## Save and verification workflow

1. Preview a specific child/date/contact with `tempus pickup --child CHILD_NAME --date YYYY-MM-DD --id PICKUP_ID --json --no-input`.
2. Review the child/date, current contact, and proposed contact. Obtain human approval for those exact values. Opening a preview is not approval to save.
3. Repeat the command with `--apply --confirm --preview-token TOKEN`. The token fingerprints the complete schedule, selected contact, and current enrollment/department/event editability metadata. The service re-reads this state under the write lock and rejects any change before posting.
4. A 0600 journal beside the session stores only hashed target/state fingerprints. It is flushed before the one POST. No authentication failure, timeout, malformed response, HTTP error, or crash causes automatic replay.
5. Read back the exact child/date and compare **every editable schedule value**, changing only `pickupId`. `scheduleTimeId` is server-generated metadata: the live API regenerates it, and post-save comparison excludes only that field. Full raw state, including IDs, still participates in the pre-save token. Success requires this comparison; response status alone is insufficient. If a response fails but the readback matches, the saved state is verified without a retry.
6. Independently read the assignment and schedule after a live test. An already assigned contact is a no-op, and an unresolved attempt is reconciled by reads before any further POST. If it still mismatches, the CLI blocks further saves; do not delete the journal and blindly retry.

Automated tests and live verification must be reported separately. No real names, identifiers, times, messages, or authentication values belong in fixtures or Git. If capturing a response for further fixtures, store raw traffic and replacement maps outside the repository, run `python -m tempus_cli.pickup_fixtures` into a private review-candidate file, then manually inspect it before adding generated placeholders to the checkout. The sanitizer cannot identify arbitrary personal text.

## Limits

- The app contract has no observed server compare-and-swap or idempotency key. A server edit between the final read and POST cannot be prevented by a client lock; subsequent verification detects a resulting mismatch. Avoid concurrent edits from other clients during the approved save.
- The private lock and journal serialize CLI processes sharing that session directory; they do not coordinate different computers/accounts.
- The CLI refuses unknown schedule/time fields, departing-alone schedules, unsupported time values, and incomplete editability metadata rather than guessing how to preserve them.
- Intersecting frozen/locked event intervals are blocked conservatively; the CLI does not attempt partial changes around them. Past dates are also blocked.
- Journal records do not expire automatically. Unresolved mismatches need explicit investigation rather than an automatic retry or rollback.

## Live verification

One explicitly approved child/date/contact assignment was saved with the installed CLI and independently read back. The HTTP response parsed successfully. The first strict raw comparison detected regenerated `scheduleTimeId`; the durable attempt blocked a retry. The original reviewed snapshot was reconstructed and matched cryptographically to its pre-save preview token, proving that only `pickupId` and the server-generated time ID differed. All times, enrollments, message, and alone flags were preserved. Verification now accounts for that observed metadata behavior, and the original attempt was reconciled through reads without another POST. A repeated approved apply was a no-op.

`pickup_write_live_shape.json` contains generated placeholders for those verified before/after schedules and the constructed request. It records the observed result without pretending that an uncaptured HTTP response body is available. The private original snapshot and personal target details are excluded from Git.
