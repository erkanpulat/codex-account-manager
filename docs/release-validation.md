# Release validation — 0.1.1

## 0.1.1 update

Checked locally on 28 September 2026: 384 tests passed. Ruff lint/format and
Mypy (68 source files) passed. New coverage checks missing, zero, partial and
malformed reset-credit responses, omission of credit identifiers, and plain-text
GUI details separate from scheduled renewals. Credit redemption is not performed.
The screenshots use synthetic profiles. For cross-platform and packaged results,
inspect the CI run associated with the release commit.

## 0.1.0 baseline

The live Desktop handoff results below were obtained for 0.1.0; these tests were
not repeated for the reset-credit display update.

Checked on Windows 11 / Python 3.13, 27–28 September 2026. These results describe
what was tested, not a guarantee that every workload or future Codex version works.

## Automated checks

- 376 tests passed locally in 55.77 seconds. Coverage includes retained Windows
  process handles, shutdown ordering, interrupted recovery, credential
  preservation, exact-turn quota verification, goal budgets and duplicate sends.
- Ruff lint and formatting passed. Mypy passed all 68 source files with Windows
  and Linux targets.
- [CI](https://github.com/erkanpulat/codex-account-manager/actions/workflows/ci.yml)
  checks Windows/Linux on Python 3.11–3.13, dependencies, static security,
  complete Git history for secrets, Python distributions and Windows packaging.
  Inspect the run for the release commit when verifying downloaded source.
- The Windows packaging job opens the real GUI in an isolated empty home and
  installs/uninstalls the installer on a disposable runner. It verifies desktop
  and Start menu shortcuts, optional startup registration, CLI startup, removal
  and preservation of synthetic user data. Release binaries are not code-signed.

## Real account and Desktop tests

Two tests used real already-limited accounts and the production watcher and
handoff code. In each test:

1. The test conversation was observed running, then failed with a real,
   structured usage-limit error on the same turn.
2. The watcher automatically selected and switched to an available account.
3. Continuation was delivered to the same Desktop conversation. Its resumed
   running turn was recorded under the destination account.
4. The conversation made a fresh Desktop browser call to `example.com`, read
   its title and completed the existing native goal.
5. All nine registered account profiles remained present.

The test harness restricted discovery to the authorized test conversation and
polled faster than the default interval. These were two independent recovery
cycles, not an unlimited unattended cascade or a long workload run until its
quota was naturally exhausted. Short turns can be missed between normal polls.

A separate controlled handoff read the active goal before and after switching:
its objective, active state, 10,000-token budget and recorded usage matched.
This establishes preservation at the handoff, not correctness of Desktop's own
subsequent usage accounting.

The live tests exposed and verified fixes for two failures: Windows process
entries can remain after termination, so shutdown checks process completion
signals; Desktop summaries can omit quota codes, so the app verifies the stored
error against the exact same failed turn. Text matching never establishes a
quota interruption.

A preparation message also timed out without a delivery receipt. Read-back
confirmed no new turn. Uncertain deliveries remain non-retryable automatically
to avoid duplicate input. The private native protocol is version-dependent;
there is no verified atomic idle-only send, so concurrent user input can race
with delivery. Failed channel verification never falls back to a separate writer.
See [continuity](continuity.md) and [security](../SECURITY.md).

## Privacy and account preservation

- Source and release archives exclude credentials, account databases, recovery
  snapshots, logs, caches and local build output. Pattern scans are useful
  evidence, not proof that every possible private value is absent.
- Documentation screenshots use synthetic profiles and contain no PNG text or
  EXIF metadata. Diagnostic exports omit aliases, paths, raw errors, logs,
  credentials and conversation content.
- Tests isolate application paths in temporary directories. Startup refuses an
  empty/missing catalogue when saved sign-in files still exist. Migration backups
  have unique names and restricted access.
- Windows MSIX filesystem redirection can expose different catalogues to
  packaged and normal processes. System check resolves the actual database path;
  the app does not automatically merge credentials between catalogues.

## Resource measurement

An earlier packaged candidate was observed with its descendants for 600.4 seconds
in an existing user session. Observed interval CPU was 26.078 seconds, with
548.25 MiB peak summed RSS and at most 16 simultaneous children. There were no
access-denied samples. Periodic samples returned to zero children between checks;
sampled idle RSS fell from 87.54 to 60.57 MiB. No continuously rising idle-memory
pattern was observed. Settings, accounts and workloads were not changed.

Sampling every 0.5 seconds can miss short-lived processes and their final CPU;
summed RSS can count shared pages more than once. This measurement predates the
process-signal and quota-summary corrections. It does not prove the absence of
all leaks or explain system-wide fan behavior. Peak memory includes Codex
subprocesses used for account and conversation reads.
