# Security policy

Security fixes target the latest development/release version. This is independent community software.

## Reporting

Use the repository's **Security → Report a vulnerability** feature if private reporting is enabled. Otherwise contact the repository maintainer privately before disclosing credentials or exploitation details. Do not post secrets in public issues.

Include the affected version, platform, reproduction steps using synthetic data, and impact. Never attach `auth.json`, profile directories, `switch.recovery.json`, unredacted logs or a database. Current diagnostic exports omit aliases, personal paths and logs; inspect archives from older versions before sharing.

## Storage and guarantees

Account Manager restricts newly written credential files to the current user, uses atomic replacement, serializes account mutations, and keeps a durable recovery snapshot during switching. Files are not encrypted and same-user software can access them. Token-shaped text is redacted from logs, including tracebacks, while diagnostic exports omit raw text entirely.

Recovery snapshots intentionally contain credentials and are excluded from exports and Git. SQLite stores account identifiers and conversation metadata but is not a credential store.

Passing tests and scanners does not guarantee the absence of every vulnerability.

## Trust boundaries and limitations

Account Manager is a local desktop utility operating with the current user's permissions. Its main sensitive operations are copying Codex credentials, changing the shared auth-store setting, starting/stopping the packaged Desktop, and restoring a native goal from an explicit local checkpoint.

### Protected boundaries

- Credential writes use randomly named exclusive temporary files, restricted ACLs or Unix `0600`, file flush/fsync and atomic replacement. Temporary files are removed after errors.
- Recovery snapshots include credentials and configuration as base64, which is encoding, not encryption. They receive the same restricted access and are removed after commit or successful rollback.
- A non-blocking OS file lock excludes concurrent account mutations. Cancellation triggers rollback; process death leaves a durable recovery snapshot.
- Profile deletion verifies that the resolved directory is a direct child of managed profiles. Shared homes, external directories and redirected paths are rejected.
- Logs redact formatted arguments and exception tracebacks. Stored event payloads and diagnostic text are also redacted. Redaction is a defensive filter, not a proof that arbitrary upstream text can never contain a secret.
- Diagnostic bundles use an allowlist of check names and status values. Profile aliases become sequential numbers. Only a validated CLI version and profile count retain detail; paths, raw errors and logs are omitted along with credentials, databases and conversation files.
- SQLite queries are parameterized. The GUI treats user-supplied account labels as plain text.
- Git ignores credential, recovery and runtime files. CI secret scanning has no blanket exclusion for docs or tests.

## Limits

Malware or another process running as the same OS user can read these files. Credentials are not encrypted at rest. Disk encryption and OS account security remain relevant. Account Manager cannot coordinate writes made by independently running Codex clients; avoid changing accounts elsewhere during a switch. Stop/save active work before switching.

Recovery covers auth/configuration files and Desktop restart attempts. Native goal writes and unrelated client activity are not a distributed transaction. A failed OS launch or unavailable Codex service can require manual recovery; diagnostics report pending snapshots.

Testing uses fake credentials and isolated storage. Release validation must distinguish those tests from a live signed-in Desktop handoff.


Automatic continuation sends model input only after a committed, identity-verified handoff and a structured usage-limit interruption. The worker inherits Codex permissions; it never supplies approval/sandbox overrides or accepts an interactive request. Native goal budgets and explicit pauses are preserved. The attempt journal records identifiers and statuses, not conversation bodies. An ambiguous send is not replayed automatically. Disable continuation in Settings to interrupt owned work; this does not stop unrelated Codex turns.


## Native Desktop delivery

Desktop continuation uses the existing local named pipe; it opens no listener or
debugging port. Before writing, the adapter checks the pipe server process path
against the official packaged Codex publisher and compares its Windows user with
the caller. Only conversation reads and continuation messages are exposed. Frame
sizes, operation time and candidate counts are bounded. Cancellation closes the
pending I/O and handles. Replies and conversation contents are not logged.

The private native protocol has no stable compatibility contract. Readiness retries
only read operations. A durable attempt is recorded before sending; uncertain
replies never cause automatic resend. Native sends do not override model, approval
or sandbox preferences. Idle checks and delivery are not atomic, so a concurrent
user action may result in Desktop queueing the follow-up. Local process compromise
under the same user remains outside this isolation boundary.
