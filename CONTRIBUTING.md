# Contributing to Codex Account Manager

Thanks for your interest in improving Codex Account Manager. This guide keeps changes
consistent and safe.

## Development setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui,dev]"
```

Requires Python 3.11–3.13 and the OpenAI Codex CLI on `PATH` for the live paths
(tests do not need it — they use fakes).

## Before opening a pull request

```powershell
.venv\Scripts\python -m ruff check src tests scripts
.venv\Scripts\python -m ruff format --check src tests scripts
.venv\Scripts\python -m mypy src
.venv\Scripts\python -m pytest -q
```

All checks must pass. CI also runs dependency auditing, secret scanning and Windows package startup verification.

## Architecture rules

- **No business logic in the CLI or GUI.** Put it in a core service
  (`accounts`, `auth`, `continuity`, `goals`, `diagnostics`, `monitoring`). The
  CLI and GUI are thin clients.
- **Talk to Codex only through adapters** (`adapters/`). Add capability
  detection rather than hard-coding version assumptions.
- **The shared home `~/.codex` is sacred.** Never split Codex history per
  profile; never delete it.
- **Auth switches are transactions.** Extend the state machine in
  `auth/transaction.py`; keep every stage journaled and reversible.

## Security rules (non-negotiable)

- Never log, print, store, or test with real credential contents.
- Route any new user-facing text through the redactor if it might contain
  secrets; add new sensitive keys to `core/redaction.py`.
- Use `os.replace` for any write to `~/.codex/auth.json`.
- Automatic switching must require a definitively limited active account and a verified available destination. Preserve explicit user mode choices; never add hidden limit-bypass behavior.

## Tests

- Unit tests go in `tests/unit`, cross-service tests in `tests/integration`.
- Use `tests/fakes.py` (`FakeAppServer`, `FakeDesktop`) instead of a real Codex.
- New features and bug fixes should come with tests.

## Commit / PR style

- Keep commits focused; write clear messages.
- PRs: summarize the change, what you tested, and any platform caveats.
- By contributing you agree your work is licensed under the MIT License.

## Code structure

`codex_account_manager` is a Python package with shared services behind a Typer CLI and native PySide6 GUI.

| Layer | Responsibility |
| --- | --- |
| `accounts` | Profile lifecycle, interactive sign-in, identity binding, bounded health reads. |
| `adapters` | Codex JSONL protocol, credential files, packaged Desktop lifecycle. |
| `auth` | Locked switching, durable recovery, rollback and commit. |
| `continuity` | Handoff records, conversation selection, switch policies. |
| `goals` | Local checkpoints and native goal reconciliation. |
| `monitoring` | Periodic health reads and policy evaluation. |
| `storage` | Parameterized SQLite repositories and transactional migrations. |
| `gui` | Presentation, asynchronous callbacks, system tray and preferences. |
| `core` | Paths, atomic writes, interprocess locks, events and redaction. |

Qt stays on the main thread. `AsyncRunner` owns a background asyncio loop and returns results through queued Qt signals. Unhandled operation errors are surfaced in the GUI. Services expose structured models; no business logic parses rendered terminal tables.

The SQLite database uses WAL and parameterized statements. Migration backups use SQLite's online backup API so WAL contents are included. Future schema versions are rejected rather than downgraded.

The account-operation file lock is distinct from the tray singleton. It serializes credential switches, sign-in and profile deletion across processes. The OS releases the lock after a crash. Shared conversation history remains in `~/.codex`; profile homes contain separate auth/configuration state.


### Finding the code

Each desktop screen has its own module under `gui`: `overview.py`, `conversations.py`,
`accounts.py`, `goals.py`, `diagnostics.py`, `settings.py`, and `about.py`.
`main_window.py` owns navigation and the system tray; `view_base.py` and `widgets.py`
provide shared UI elements. Screen widgets call services rather than writing credentials.

The top-level `src` directory contains application code, `tests` contains isolated
unit/integration checks, `docs` explains behavior, `scripts` contains development tools,
and `packaging` builds Windows distributions. Virtual environments, build outputs,
logs, account data, recovery snapshots and caches are ignored by Git.

## Codex integration

The adapter starts `codex app-server --listen stdio://`, performs `initialize` / `initialized`, and exchanges JSONL messages over pipes. It prefers a native executable on Windows; a command-shim fallback rejects shell metacharacters.

A dedicated reader matches replies by ID. Unexpected non-object JSON is ignored, unsupported server requests receive a method error, and request timeouts/cancellation remove pending futures. Standard error is discarded to avoid a blocked pipe or persistence of unredacted upstream output. Process shutdown closes pipes and terminates a child that will not exit.

Account reads prefer the `codex` entry in `rateLimitsByLimitId`, with the legacy `rateLimits` view as fallback. Unknown fields remain unknown. A bound identity must match before credentials are activated.

`thread/resume` loads a stored conversation for later turns; it does not send `turn/start`. Goal endpoints vary by Codex version. Account Manager checks their result when used and treats an unavailable native goal read as unverified. It never advertises an unprobed write method as a detected capability.

Reference: [official Codex App Server documentation](https://developers.openai.com/codex/app-server/).

Conversation listing follows every cursor, requests all source kinds and all model providers, and sorts by updated activity. A complete successful response replaces the visible local snapshot transactionally; a failure preserves the previous list. Archived/removed rows retain local checkpoints but disappear from the list. The current protocol provides `name`, `cwd`, `source`, `projectId` and recency metadata. Folder grouping provides a fallback when `projectId` is absent; it is not cloud project synchronization. See the [current official protocol documentation](https://learn.chatgpt.com/docs/app-server).


CLI continuation uses a separate, long-lived connection with experimental APIs enabled for `thread/turns/list` (limit 1, no item bodies). It verifies the last turn, resumes the same thread with `excludeTurns`, checks idle status, sends `turn/start`, and waits for its matching `turn/completed` notification. Cancellation or interactive requests interrupt only the owned turn. It never changes approval or sandbox policies. Goal reactivation updates only `status`; budget and accumulated usage must remain intact. Continuation method errors stop automation rather than guessing capability support.

## Interface maintenance

English and Turkish messages live in `gui/i18n.py`. Keep Qt work on the main
thread and use the shared widgets, spacing and icon helpers. Run
`python scripts/render_preview.py` to regenerate actual-widget screenshots with
synthetic profiles; never use real accounts in documentation images.
`python scripts/build_icons.py` generates the Windows icon sizes.
