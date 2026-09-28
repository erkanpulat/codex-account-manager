# Account switching and continuity

A handoff switches the shared Codex login and may load a chosen conversation. Automatic continuation is a separate step after that transaction commits; model work is never started inside a transaction that might roll back. Desktop work uses the running Desktop native tool channel; CLI work uses an App Server connection. Both verify the exact interruption before sending input.

## Transaction boundary

1. Acquire the account operation lock. Recover any earlier interrupted switch.
2. Require credentials and a bound target identity. With the real adapter, preserve refreshed active credentials in their matching profile and verify the target before stopping Desktop.
3. Write a durable, restricted-access snapshot of the previous `auth.json` and `config.toml`.
4. Stop only the packaged Codex Desktop processes, parent first. Verify Windows process completion signals rather than waiting for PID removal; inaccessible processes do not count as stopped. Persist the recovery marker before configuring file-based auth or atomically replacing shared credentials.
5. Verify the active identity and restart Desktop. A readiness timeout is a failure.
6. Record commit, then delete the recovery snapshot. This deletion is the commit point.
7. If requested, load the conversation and reconcile its checkpoint after commit. A load or reconciliation error is reported separately and does not undo a verified account switch. Automatic model work starts only if this step succeeds.

Exceptions and coroutine cancellation after credential mutation may have started restore the snapshot. Before that point, recovery preserves the current credentials and does not repeat Desktop shutdown; if the previously running Desktop has exited, it is relaunched. Once the account switch commits, conversation loading cannot roll it back; failures are recorded for user attention. If rollback itself fails, the snapshot remains for recovery on the next launch/switch. The stage journal contains no credential payload. Database handoff history records the outcome but is not the recovery authority. A process termination can leave a history row pending; the filesystem snapshot determines whether credentials need restoration.

## Policies

`manual` never initiates a switch. `confirm` presents a suggestion in the GUI. `availability_failover` switches automatically only when the current profile is definitively limited and the destination has credentials, a matching bound identity, and a known available quota state. Unknown accounts are not considered available.

New installations default to `availability_failover`. Existing explicit choices are preserved. The GUI polls every 60 seconds by default; Settings accepts 30–3600 seconds. A saved setting wakes the watcher immediately and it reloads the policy and interval before its next check. Monitoring requires the GUI/tray process to remain running. After a failed automatic switch, the watcher waits at least five minutes before retrying the same source and destination, doubling the delay up to 30 minutes. This avoids restarting Desktop on every poll. A different target can be tried immediately. Automatic failover discovers running work among the 20 most recently updated non-subagent conversations and keeps previously observed work under observation. Observation uses at most four concurrent conversation reads, a two-second per-conversation deadline and a ten-second scan budget. The overall check allows thirty seconds including connection startup. Successful observations are published immediately; unavailable conversations keep their previous observations and produce a partial result. Only a verified limit transition on that same turn and source account is eligible. If none qualifies, it switches accounts without loading an unrelated conversation. This can differ from the window currently visible in Desktop; use an explicit CLI `--thread` when the exact conversation matters.

## Goals

Only explicit checkpoints are restored. A conversation preview never becomes an invented goal. Paused, blocked, completed, failed, or locally user-cleared checkpoints are not reactivated. Unsupported or failed native goal reads cause a visible blocked result rather than guessing that the goal is missing.

The local checkpoint stores an objective and revision. Native goal token budgets are not recreated. Clearing a local checkpoint prevents future restoration but does not delete the native Codex goal.

Saving a local goal note does not call the native goal API or start a turn. Reading a Codex goal is also read-only. On a later load/handoff, a confirmed missing native goal may be restored from an active local note. Native `budgetLimited` remains blocked. A verified `usageLimited` goal may be reactivated after a successful account handoff when automatic continuation is enabled. Only its status is changed; the objective, token budget and accumulated usage are verified and preserved. Native read failures are stored as unknown, not as proof of absence. The API cannot distinguish an externally deleted goal from a goal lost during a handoff: clear the local note as well when you no longer want restoration.

## Desktop ownership

Desktop conversations are not resumed through a separate App Server. The native
adapter discovers the local Windows named pipe, verifies that its server is the
packaged Codex Desktop process owned by the same Windows user, and calls Desktop's
`read_thread` and `send_message_to_thread` operations. No CDP/debugging port is
opened, no application bundle is patched, and no model, approval or sandbox
setting is overridden. The continuation stays with Desktop's own runtime.

After switching, the pending record is bound to the destination account. Before
sending, the worker rechecks the account, exact source turn, structured limit,
goal fingerprint and local continuation preference. A durable claim precedes the
request. Lost replies are marked uncertain and never automatically retried.
The next observed running Desktop turn is tracked under the destination account.
Post-send observation has a ten-second total deadline; a timeout preserves the
submitted claim and reports that attention is needed, without resending input.
A task that starts and ends between observations may still be missed.

This native protocol is private and version-dependent. The implementation was
informed by [codex-mcp-bridge's native relay](https://github.com/buidangminh23/codex-mcp-bridge/blob/main/src/native-relay.mjs).
Two live tests triggered real quota errors on already-limited accounts. Each
passed automatic switching, continuation in the same Desktop test conversation,
a fresh interactive browser call, goal completion and destination-account tracking.
The test harness narrowed observation to that conversation and polled more often
than the default interval. See [validation scope](release-validation.md).
If the channel cannot be verified, the app reports the failure and keeps the
pending work; it never silently transfers ownership to a headless process.

The existing-chat deep link remains a manual navigation action and sends no input.
The native interface has no verified atomic idle-only send operation. A user can
start a new turn between the final idle check and delivery; Desktop may queue the
follow-up. This race is not eliminated by the durable duplicate-attempt guard.

## Automatic work after a limit

Each monitoring check persists observations of running conversations before
deciding whether to switch accounts. A usage-limit interruption is eligible only
when the same turn was previously observed running under the same account, with
the same goal fingerprint. Historical limit errors discovered at startup are
not resumed automatically. Discovery inspects the
20 most recent main conversations; previously observed conversations remain under
observation even after they fall outside that window. This follows the configured
poll interval, not a real-time subscription. A tracking pass has a 30-second budget, including connection startup;
conversation scanning is bounded to ten seconds with four concurrent reads.
Bounded discovery uses the state database. Desktop activity is read from Desktop
itself. If a failed Desktop summary omits its structured error code, the app
reads stored turn history and accepts the code only when the turn ID and failed
state match exactly. Human-readable error text is never quota evidence.
Other sources can use a bounded 4 MiB rollout lifecycle tail when stored
turn history is ambiguous. Partial, stale, or changed files remain unknown. The
UI displays check progress, partial results, and failures.

The local database stores a hash of the source account ID, the exact thread and
turn IDs, the turn state, observation time, and a fingerprint of the native goal's
identity and budget. It does not copy conversation text or the goal objective.
Records survive application restarts. A completed account handoff consumes its
pending records so they are not reused on a later switch. Completed,
user-interrupted, or missing work is removed from pending observations. An
unverifiable observation is held for revalidation. Limit records older than one
hour are not selected without a fresh observation.

The Conversations page shows recent tracked work with its conversation title,
account, observed turn state, native Codex goal state, and last check time. It
does not store the goal objective; selecting a row and choosing **Read selected
Codex goal** requests the current goal from Codex. The list is limited to the
50 most recently observed records from the past 24 hours. The full local
conversation history below it is separate and does not imply that every listed
conversation is being tracked or will resume automatically.

Before switching, the saved interruptions are revalidated. After switching, they
are processed sequentially, with the exact turn and goal checked again before
sending input. Changed or missing goals are not reconstructed from stale records.
This persistence improves selection; it cannot make a Desktop-only goal readable
through an App Server that does not expose that goal.

The default `auto_continue=true` preference is independent of the switching policy. Manual switching and ordinary conversation loading do not start work. A limit-driven handoff requires a previously observed running turn on the source account followed by a structured `usageLimitExceeded` error, or a native `usageLimited` goal after that turn completes. Recency alone, an interrupted turn, an arbitrary error, an active goal alone or a local note is not evidence of a usage-limit interruption. When none qualifies, the app switches accounts but reports that continuation was skipped.

Before sending input, the worker rechecks the exact turn, target account, user setting and local/native goal states. The thread must be idle. It holds the account-operation lock while working; stop continuation before manually switching accounts or editing account credentials. A durable journal claims each source turn before input is sent. Lost acknowledgements or process crashes are not blindly retried; inspect the conversation when the app reports that attention is required.

For CLI/App Server sources, the worker sends `turn/start` and consumes notifications until completion. Without a native goal, it runs one continuation turn. With an active goal, it rechecks state and continues until the goal completes, pauses, becomes blocked, exhausts its budget or requests intervention. Another verified account limit can trigger another handoff on the next monitoring check. A changed conversation, unsupported API, unknown goal state or other error stops automation visibly. The App Server does not currently expose an atomic idle-only `turn/start`: another client can start a turn between the idle check and the request, in which case Codex may steer the continuation input into that active turn. Disable automatic continuation if this race is unacceptable for your workflow.

Approval and user-input requests are never accepted automatically. The worker interrupts its own turn and asks the user to open the conversation in Codex. The separate connection cannot forward Desktop-specific interactive tools or guarantee that Desktop immediately displays its output; inspect/reload the same conversation there. Disabling continuation cancels the owned turn. Closing Account Manager also stops its worker. Completed and uncertain attempts are retained across restarts to prevent duplicate input.

The latest-turn query requires the experimental `thread/turns/list` method.
Neither polling nor a successful live test guarantees unattended completion of
every workload. An unsupported Codex version, an unobserved short turn, a changed
goal or uncertain delivery stops continuation for review.
