# Account switching and continuity

A handoff switches the shared Codex login and may load a chosen conversation. Automatic continuation is a separate step after that transaction commits; model work is never started inside a transaction that might roll back. Desktop work uses the running Desktop native tool channel; CLI work uses an App Server connection. Both verify the exact interruption before sending input.

## Transaction boundary

The Windows GUI delegates startup through the existing Explorer desktop's `Document.Application`, before acquiring its singleton or opening user state. Creating a new `Shell.Application` object and calling `ShellExecute` directly is insufficient: a process can retain the launcher's Windows job membership even when Explorer appears as its parent. The isolated Windows lifetime test terminates the launcher's job and verifies that the delegated child survives. The internal `--from-windows-shell` argument prevents recursive delegation; it is not a public launch mode.

Windows job inheritance and termination behavior are described in Microsoft's [nested jobs documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs).

Automatic failover separates conversation failures from shared resources. An unreadable IDE or CLI conversation is excluded from continuation and reported individually; verified work can still switch accounts. Running or unverified Desktop conversations defer the shared Desktop restart. Unknown ownership also defers that restart. Failed preparation blocks it only when the conversation depends on Desktop. Manual switches remain explicit operations. The scan is bounded and does not provide an atomic lock against another client starting work immediately afterward.

After a committed switch, Desktop and IDE have independent continuation queues; CLI conversations run independently. Work sharing an IDE restart remains serialized. Native attempts have a three-minute deadline, and preparation has a twelve-second deadline per conversation. Concurrent workers share one account-session lock so a login cannot change underneath them; the final worker releases it even on cancellation. Each conversation loads in its own worker, so one load failure does not discard other prepared conversations. Jobs retains per-conversation results, and a successful submission does not dismiss another conversation's warning.

Quota handoffs recheck shared Desktop work after target verification, inside the account-operation lock and before stopping Desktop. New running work, an unverified Desktop state, a changed account or paused/reset monitoring defers the switch. This narrows the observation-to-restart gap; upstream clients do not expose an atomic lock against starting a new turn. Disabling IDE continuation cancels only IDE workers and discards their waiting requests. Global continuation or monitoring controls retain their global scope.

Verified tickets are persisted before shutdown in `pending_continuations`, without credentials or conversation text. After an unexpected process exit, enabled monitoring can recover tickets less than ten minutes old on the same destination account. The normal continuation worker rechecks the exact turn, goal, permissions and durable send claim. Changed accounts, stale tickets or disabled continuation are reported and removed; an uncertain send is never retried. Clearing tracked work also clears pending tickets.

If Desktop or the IDE owner is not ready during the first bounded read after switching, an **unsent** ticket remains pending for the next monitoring poll, for at most ten minutes from preparation. A temporary failure to read the active account also preserves it. No delivery is retried after a send claim. Pausing monitoring clears waiting tickets. The UI distinguishes waiting for a connection from an operation requiring user attention.

Historical failures present at the first observation are not automatically revived. A newer IDE turn can qualify between observations as described below. In Jobs, **Continue after verified limit** explicitly queues a selected conversation after confirmation. This requires monitoring and automatic continuation to be enabled, verified capacity on the active account, a current structured quota failure, an allowed unchanged goal and no previous send claim for that turn. Queueing does not establish successful continuation or verify an IDE's cached account. It may consume quota when the worker sends the request.

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

New installations preselect `availability_failover` and `monitor_enabled` defaults to true. Pause monitoring in Overview or Settings; pausing leaves the watcher asleep until a settings change or an on-demand check. Existing explicit policy choices are preserved. While enabled, the GUI polls every 60 seconds by default; Settings accepts 30–3600 seconds. A saved setting wakes the watcher immediately and it reloads the policy and interval before its next check. Monitoring requires the GUI/tray process to remain running. Closing the window exits unless `keep_in_tray` is explicitly enabled; tray status makes that choice visible. An on-demand check while paused cannot switch accounts. After a failed automatic switch, the watcher waits at least five minutes before retrying the same source and destination, doubling the delay up to 30 minutes. This avoids restarting Desktop on every poll. A different target can be tried immediately. Automatic failover discovers running work among the 20 most recently updated non-subagent conversations and keeps previously observed work under observation. Observation uses at most four concurrent conversation reads, a two-second per-conversation deadline and a ten-second scan budget. The overall check allows thirty seconds including connection startup. Successful observations are published immediately; unavailable conversations keep their previous checkpoints but are marked unverified and produce a partial result. A successful full list removes observations of deleted conversations. Only a verified limit transition on that same turn and source account is eligible. If none qualifies, it switches accounts without loading an unrelated conversation. This can differ from the window currently visible in Desktop; use an explicit CLI `--thread` when the exact conversation matters.

## Goals

Only explicit checkpoints are restored. A conversation preview never becomes an invented goal. Paused, blocked, completed, failed, or locally user-cleared checkpoints are not reactivated. Unsupported or failed native goal reads cause a visible blocked result rather than guessing that the goal is missing.

The local checkpoint stores an objective and revision. Native goal token budgets are not recreated. Clearing a local checkpoint prevents future restoration but does not delete the native Codex goal.

Saving a local goal note does not call the native goal API or start a turn. Reading a Codex goal is also read-only. On a later load/handoff, a confirmed missing native goal may be restored from an active local note. Native `budgetLimited` remains blocked. A verified `usageLimited` goal may be reactivated after a successful account handoff when automatic continuation is enabled. Only its status is changed; the objective, token budget and accumulated usage are verified and preserved. Native read failures are stored as unknown, not as proof of absence. The API cannot distinguish an externally deleted goal from a goal lost during a handoff: clear the local note as well when you no longer want restoration.

## Source and runtime verification

Only `cli`, `exec` and `appServer` sources are eligible for headless continuation.
The shared `vscode` source identifies a Desktop/IDE family, not a verified owner.
Unknown and subagent sources do not fall back to Desktop. Desktop tickets require
a matching native turn and goal fingerprint before switching and are revalidated
after the switch. A missing native connection prevents ticket creation; it is not
permission to transfer IDE work to another runtime. Native read access remains
version-dependent and does not establish an atomic ownership lock.

The UI's support check is read-only, bounded to twelve seconds plus subprocess
cleanup, and starts only on request. Its result indicates source/connection
availability, not eligibility for automatic continuation or proof of an IDE's
active account. IDE-native continuation is opt-in and experimental, as described below. Project navigation
passes one local directory to a detected editor executable without a shell,
credential changes, process termination or model input.

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

Before switching, the saved interruptions are revalidated. After switching, independent
queues process them, with the exact turn and goal checked again before
sending input. Changed or missing goals are not reconstructed from stale records.
This persistence improves selection; it cannot make a Desktop-only goal readable
through an App Server that does not expose that goal.

The default `auto_continue=true` preference is independent of the switching policy. Manual switching and ordinary conversation loading do not start work. A limit-driven handoff requires a previously observed running turn on the source account followed by a structured `usageLimitExceeded` error, or a native `usageLimited` goal after that turn completes. Recency alone, an interrupted turn, an arbitrary error, an active goal alone or a local note is not evidence of a usage-limit interruption. When none qualifies, the app switches accounts but reports that continuation was skipped.

Before sending input, the worker rechecks the exact turn, target account, user setting and local/native goal states. The thread must be idle. It holds the account-operation lock while working; stop continuation before manually switching accounts or editing account credentials. A durable journal claims each source turn before input is sent. Lost acknowledgements or process crashes are not blindly retried; inspect the conversation when the app reports that attention is required.

For CLI/App Server sources, the worker sends `turn/start` and consumes notifications until completion. Every 30 seconds without a terminal notification, it reads the exact owned turn to detect a missed completion or failed connection. Without a native goal, it runs one continuation turn. With an active goal, it rechecks state and continues until the goal completes, pauses, becomes blocked, exhausts its budget or requests intervention. Another verified account limit can trigger another handoff on the next monitoring check. A changed conversation, unsupported API, unknown goal state or other error stops that conversation's automation visibly. The App Server does not currently expose an atomic idle-only `turn/start`: another client can start a turn between the idle check and the request, in which case Codex may steer the continuation input into that active turn. Disable automatic continuation if this race is unacceptable for your workflow.

Approval and user-input requests are never accepted automatically. The worker interrupts its own turn and asks the user to open the conversation in Codex. The separate connection cannot forward Desktop-specific interactive tools or guarantee that Desktop immediately displays its output; inspect/reload the same conversation there. Disabling continuation cancels the owned turn. Closing QuotaCrew also stops its worker. Completed and uncertain attempts are retained across restarts to prevent duplicate input.

The latest-turn query requires the experimental `thread/turns/list` method.
Neither polling nor a successful live test guarantees unattended completion of
every workload. An unsupported Codex version, an unobserved short turn, a changed
goal or uncertain delivery stops continuation for review.


## Experimental local IDE continuation

The unreleased source checkout includes `ide_continue=false` by default. When enabled, local `vscode`-family conversations use their existing Codex owner over the Windows `codex-ipc` router. The router process must belong to the same Windows user and match packaged Codex Desktop or a detected standard editor executable. Remote, WSL and cloud owners are not supported. Opening an editor folder is separate from sending model input.

The adapter discovers the owner, reads its latest turn, pending requests and goal, and rechecks ownership before sending. It inherits thread settings without overriding tools, model, approvals, sandbox or goal budgets. Busy/unknown state stops submission. A durable input claim prevents blind retries after an uncertain response; no separate CLI writer is started. Owner checks are not an atomic lock against another client starting a turn.

Desktop and a local IDE can be open together. QuotaCrew does not install an editor extension; the IDE must already have OpenAI's Codex extension and an open local Codex conversation. VS Code's separate built-in chat providers are not Codex owners. A validated `Codex Desktop` originator uses the Desktop native channel even when IDE continuation is enabled. Other local owners use the IDE router; a routing failure does not start a separate writer.

A failed owner's `systemError` is eligible only when the stored error on that exact turn verifies a quota failure; approvals, outstanding submissions and other runtime states still block delivery. After a committed account switch, the restarted owner's identity is discovered again with a bounded wait. Subsequent checks and submission must retain that identity and the original turn and goal. One failed conversation does not abort the remaining batch. Jobs → row menu → **Automatic continuation details** retains the latest 20 safe status/stage records; older versions did not record these details. No conversation text or raw error is saved in these records.

This uses private protocol versions (discovery v1, snapshot v11, start-turn v2). IDE reads allow 16 MiB per frame, 32 MiB total and 64 messages, with cancellation and deadlines. Pipe reads use chunks of at most 64 KiB. Oversized responses produce a specific size warning instead of implying the editor is closed. The account cached inside the running extension is not independently readable. On 1 October, a controlled continuation initially failed at the old quota despite available shared credentials, then ran after refreshing VS Code and reopening the exact conversation. This verifies that local recovery case, not every editor version or an unattended combined quota cycle.

**Optional VS Code refresh (`ide_refresh=false` by default).** Enable it under Settings → Conversations together with IDE continuation. Before a verified IDE continuation, the worker checks all discovered local IDE owners for running work or pending approvals. Only an explicit `no-client-found` discovery response can be skipped; other unknown states stop refresh. Exactly one same-user standard VS Code window and an existing local workspace are required. The app sends a normal close request, waits up to 30 seconds without terminating the process or dismissing save dialogs, reopens the interrupted conversation's workspace, and routes `vscode://openai.chatgpt/local/<thread-id>` to the installed extension. VS Code's URI consent may need user approval; it is never suppressed. A fresh owner and the unchanged interrupted turn/goal are verified before sending. One account/process generation is refreshed once per supervisor lifetime. Cursor, Windsurf, multiple VS Code windows and remote/WSL workspaces are not supported by automatic refresh. Desktop tickets never enter this path.

While monitoring, all supported conversation sources retain a latest-turn baseline. A newer turn with a verified quota error can be selected even if it began and failed between polls, provided the account, goal and tracking generation remain unchanged. A persisted running observation also covers this transition after restarting QuotaCrew. The first observed historical failure is never automatically revived. Pausing/resetting observation clears the baseline. Polling can still miss a conversation that has never been observed.

During IDE startup, missing, busy or broken Windows pipes are treated as temporary read failures. Read-only discovery waits for the owner; an unsent ticket remains pending for up to ten minutes. The same transport failure during message submission is uncertain delivery and is never automatically replayed. Desktop jobs continue in their separate queue while the IDE reconnects.

The Desktop relay label is not evidence of IDE delivery. Jobs → row menu → **Automatic continuation details** distinguishes preparation, editor refresh, connection waiting, submission and observed results.

## Optional Windows shutdown

Shutdown is off by default and never persisted. Each application session needs explicit confirmation for one of three modes:

- **Selected work:** choose a conversation on the shutdown page or use its work-menu action. Its exact turn or goal must complete successfully. Errors, limits, changed goals and requests for input are not completion.
- **All limits:** every saved account must have freshly verified exhausted usage and no available reset credits. An unfinished goal alone does not prevent this mode once its turn has stopped; a running or unverified turn does.
- **Timer:** choose 1–1440 minutes from confirmation (120 minutes = two hours). The last two minutes are the warning period, included in the total duration. A one-minute plan warns immediately. This mode is independent of account checks, continuation and monitoring, and does not wait for Codex work to finish.

Work and limit modes wait for other observed Codex work to stop, then start a fixed 120-second countdown. Checks run every 60 seconds while waiting, every 15 seconds during the countdown, and once more before execution. Missing fresh evidence resets that countdown. Unknown quota, missing runtime information or work that cannot be verified keep the plan waiting.

The page, application banner and tray menu show the active plan and allow cancellation. Quitting or closing without tray mode cancels every plan. Pausing monitoring cancels conditional plans but leaves an explicitly scheduled timer running. This only observes supported local Codex work, not unsaved documents or activity in other programs. A new task can still start after the final check.

The fixed Windows command uses the system `shutdown.exe /s /t 0` with no `/f`, shell, elevation or background helper. The countdown belongs to QuotaCrew: using a positive Windows `/t` would implicitly force applications closed. Windows may refuse or delay shutdown when applications need attention. Tests replace the shutdown function; the test suite never shuts down the machine.
