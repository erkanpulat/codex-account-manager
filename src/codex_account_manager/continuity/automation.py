"""Supervised continuation after a verified usage-limit handoff.

Claims are persisted before sending input. An uncertain delivery is never replayed.
No conversation content or model output is stored in the attempt journal.

This module does not bypass rate limits or manipulate quotas. It monitors for a
``usageLimitExceeded`` error and switches to a *separate, independently registered*
account. Users are responsible for complying with all applicable terms of service.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, replace
from hashlib import sha256
from uuid import uuid4

from codex_account_manager.adapters.app_server import CodexAppServer
from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.adapters.native_desktop import NativeDesktop, verified_desktop_turn
from codex_account_manager.continuity.tracking import WorkTracker, goal_signature
from codex_account_manager.core.errors import AppServerError
from codex_account_manager.core.events import bus
from codex_account_manager.core.operation_lock import OperationLock
from codex_account_manager.core.paths import paths
from codex_account_manager.domain.states import GoalState
from codex_account_manager.goals.service import GoalService
from codex_account_manager.storage.database import connect
from codex_account_manager.storage.repositories import SettingsRepository

DESKTOP_OBSERVATION_SECONDS = 10.0


@dataclass(frozen=True)
class ContinuationTicket:
    thread_id: str
    turn_id: str
    account_id: str | None = None
    goal_signature: str | None = None
    desktop: bool = False


def goal_allows_continuation(goal: GoalInfo | None) -> bool:
    if goal is None:
        return False
    if not goal.present:
        return True
    if goal.status not in {"active", "usageLimited"}:
        return False
    budget, used = goal.token_budget, goal.tokens_used
    if not isinstance(used, int) or isinstance(used, bool) or used < 0:
        return False
    return budget is None or (
        isinstance(budget, int) and not isinstance(budget, bool) and used < budget
    )


def has_verified_limit_turn(turn: dict | None, goal: GoalInfo | None) -> bool:
    if not turn or not goal_allows_continuation(goal):
        return False
    error = turn.get("error")
    if turn.get("status") == "failed":
        return isinstance(error, dict) and error.get("codexErrorInfo") == "usageLimitExceeded"
    return bool(
        turn.get("status") == "completed"
        and goal is not None
        and goal.present
        and goal.status == "usageLimited"
    )


class ContinuationSupervisor:
    def __init__(self, *, factory: Callable[[], CodexAppServer] | None = None):
        self.factory = factory or (
            lambda: CodexAppServer(paths.shared_codex_home, experimental=True)
        )
        self.native = NativeDesktop()
        self.tasks: set[asyncio.Task] = set()
        self.goals = GoalService()
        self.tracker = WorkTracker()

    async def enabled(self) -> bool:
        return await SettingsRepository().get("auto_continue", "true") == "true"

    async def _local_allows(self, thread_id: str) -> bool:
        checkpoint = await self.goals.get(thread_id)
        if checkpoint is None:
            return True
        if checkpoint.user_cleared:
            return False
        # Reconciliation marks a native usage limit as blocked. Only that specific
        # account-limit state may be resumed; user pauses and goal budgets remain intact.
        return checkpoint.local_status in {
            GoalState.ACTIVE,
            GoalState.ACTIVE_AFTER_HANDOFF,
            GoalState.SWITCHING,
            GoalState.RESUMING,
        } or (
            checkpoint.local_status == GoalState.BLOCKED
            and checkpoint.native_goal_status == "usageLimited"
        )

    async def prepare(self, thread_id: str) -> ContinuationTicket | None:
        if not await self.enabled() or not await self._local_allows(thread_id):
            return None
        adapter = self.factory()
        try:
            await adapter.start()
            await adapter.require_headless_compatible(thread_id)
            turn = await adapter.latest_turn(thread_id)
            goal = await adapter.get_goal(thread_id)
            if goal is None:
                raise AppServerError("Could not verify the goal before preparing continuation.")
            if not turn or not has_verified_limit_turn(turn, goal):
                return None
            return ContinuationTicket(thread_id, turn["id"], goal_signature=goal_signature(goal))
        finally:
            await adapter.aclose()

    def launch_batch(self, tickets: list[ContinuationTicket]) -> None:
        async def run_all() -> None:
            for ticket in tickets:
                if not await self.enabled():
                    break
                await self.run(ticket)

        task = asyncio.create_task(run_all())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def stop(self) -> None:
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _claim(self, ticket: ContinuationTicket) -> str | None:
        message_id = str(uuid4())
        async with connect() as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO continuation_attempts VALUES (?, ?, ?, 'sending')",
                (ticket.thread_id, ticket.turn_id, message_id),
            )
            await db.commit()
            return message_id if cursor.rowcount == 1 else None

    async def _record(self, ticket: ContinuationTicket, status: str) -> None:
        async with connect() as db:
            await db.execute(
                "UPDATE continuation_attempts SET status=? WHERE thread_id=? AND source_turn_id=?",
                (status, ticket.thread_id, ticket.turn_id),
            )
            await db.commit()

    async def run(self, ticket: ContinuationTicket) -> None:
        if ticket.desktop:
            await self._run_desktop(ticket)
            return
        adapter = self.factory()
        claimed: ContinuationTicket | None = None
        key = sha256(ticket.thread_id.encode()).hexdigest()
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()

        def stop_requested(_event) -> None:
            if task:
                loop.call_soon_threadsafe(task.cancel)

        unsubscribe = bus.subscribe("continuation.stop", stop_requested)
        locks = ExitStack()
        stage = "connection"
        try:
            locks.enter_context(
                OperationLock(paths.data_dir / "locks" / f"continuation-{key}.lock")
            )
            locks.enter_context(OperationLock(paths.data_dir / "account-operation.lock"))
            await adapter.start()
            stage = "account"
            account_id = ticket.account_id
            if not account_id or (await adapter.read_account()).account_id != account_id:
                raise AppServerError("The active account changed before continuation.")
            stage = "conversation"
            await adapter.resume_for_continuation(ticket.thread_id)
            while await self.enabled():
                stage = "verification"
                if not await self._local_allows(ticket.thread_id):
                    break
                latest = await adapter.latest_turn(ticket.thread_id)
                if (
                    not latest
                    or latest["id"] != ticket.turn_id
                    or latest.get("status") not in {"failed", "completed"}
                ):
                    raise AppServerError(
                        "Conversation changed; automatic continuation was skipped."
                    )
                stage = "goal"
                goal = await adapter.get_goal(ticket.thread_id)
                if goal is None:
                    raise AppServerError("Could not verify the goal before continuation.")
                if ticket.goal_signature and goal_signature(goal) != ticket.goal_signature:
                    raise AppServerError("The goal changed after the interruption was recorded.")
                if not goal_allows_continuation(goal):
                    break
                stage = "journal"
                message_id = await self._claim(ticket)
                if message_id is None:
                    raise AppServerError(
                        "This continuation was already attempted. Inspect the conversation before retrying."
                    )
                claimed = ticket
                if goal and goal.status == "usageLimited":
                    stage = "goal"
                    await adapter.reactivate_usage_limited_goal(ticket.thread_id, goal)
                    await self.goals.resumed_usage_limited_goal(ticket.thread_id)
                    goal = replace(goal, status="active")
                bus.publish("continuation.status", state="running")
                stage = "execution"

                async def started(
                    turn_id: str, thread_id: str = ticket.thread_id, observed_goal: GoalInfo = goal
                ) -> None:
                    await self.tracker.observe(
                        account_id,
                        thread_id,
                        {"id": turn_id, "status": "inProgress"},
                        observed_goal,
                    )
                    bus.publish("work.observed")

                completed = await adapter.run_continuation_turn(
                    ticket.thread_id,
                    message_id,
                    on_started=started,
                )
                status = completed.get("status")
                if status not in {"completed", "failed", "interrupted"}:
                    raise AppServerError("Codex returned an invalid turn result.")
                await self._record(ticket, str(status))
                claimed = None
                current_goal = await adapter.get_goal(ticket.thread_id)
                if current_goal is not None or status == "interrupted":
                    await self.tracker.observe(
                        account_id,
                        ticket.thread_id,
                        completed,
                        current_goal,
                        limited=has_verified_limit_turn(completed, current_goal),
                    )
                    bus.publish("work.observed")
                if status == "interrupted":
                    bus.publish("continuation.status", state="stopped")
                    return
                if status != "completed":
                    # The watcher can perform another handoff if the new account
                    # is actually limited. Other failures require user attention.
                    bus.publish("continuation.status", state="needs_user")
                    return
                stage = "goal"
                goal = current_goal
                if goal is None:
                    raise AppServerError("Could not verify the goal after continuation.")
                if not goal.present or goal.status in {"complete", "completed"}:
                    if goal.present:
                        await self.goals.mark_status(ticket.thread_id, GoalState.COMPLETE)
                    bus.publish("continuation.status", state="completed")
                    return
                if goal.status != "active" or not goal_allows_continuation(goal):
                    break
                ticket = ContinuationTicket(
                    ticket.thread_id, completed["id"], ticket.account_id, ticket.goal_signature
                )
                # Re-check user settings and persisted turn state before every turn.
                await asyncio.sleep(0)
            bus.publish("continuation.status", state="stopped")
        except asyncio.CancelledError:
            if claimed:
                await self._record(claimed, "interrupted")
            bus.publish("continuation.status", state="stopped")
            raise
        except Exception:
            if claimed:
                await self._record(claimed, "uncertain")
            # Server output may contain conversation content: only publish a safe status.
            bus.publish("continuation.status", state="needs_user", stage=stage)
        finally:
            unsubscribe()
            try:
                await adapter.aclose()
            finally:
                locks.close()

    async def _run_desktop(self, ticket: ContinuationTicket) -> None:
        adapter = self.factory()
        claimed = False
        key = sha256(ticket.thread_id.encode()).hexdigest()
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()

        def stop_requested(_event) -> None:
            if task:
                loop.call_soon_threadsafe(task.cancel)

        unsubscribe = bus.subscribe("continuation.stop", stop_requested)
        locks = ExitStack()
        try:
            locks.enter_context(
                OperationLock(paths.data_dir / "locks" / f"continuation-{key}.lock")
            )
            locks.enter_context(OperationLock(paths.data_dir / "account-operation.lock"))
            await adapter.start()
            if not await self.enabled() or not await self._local_allows(ticket.thread_id):
                return
            if (
                not ticket.account_id
                or (await adapter.read_account()).account_id != ticket.account_id
            ):
                raise AppServerError("The active account changed before Desktop continuation.")
            latest = await verified_desktop_turn(self.native, adapter, ticket.thread_id, wait=True)
            goal = await adapter.get_goal(ticket.thread_id)
            if (
                latest.get("id") != ticket.turn_id
                or not has_verified_limit_turn(latest, goal)
                or goal is None
                or goal_signature(goal) != ticket.goal_signature
            ):
                raise AppServerError("The Desktop interruption or goal changed.")
            # Re-read just before the durable claim; never steer a known running turn.
            current = await verified_desktop_turn(self.native, adapter, ticket.thread_id)
            if current.get("id") != ticket.turn_id or current.get("status") != latest.get("status"):
                raise AppServerError("The Desktop conversation is no longer idle.")
            if not await self.enabled() or not await self._local_allows(ticket.thread_id):
                return
            if (await adapter.read_account()).account_id != ticket.account_id:
                raise AppServerError("The account changed during Desktop verification.")
            final_goal = await adapter.get_goal(ticket.thread_id)
            if (
                final_goal is None
                or not has_verified_limit_turn(current, final_goal)
                or goal_signature(final_goal) != ticket.goal_signature
            ):
                raise AppServerError("The goal changed during Desktop verification.")
            if await self._claim(ticket) is None:
                raise AppServerError("Desktop continuation was already attempted.")
            claimed = True
            await self.native.send(ticket.thread_id, ticket.turn_id)
            await self._record(ticket, "submitted")
            claimed = False
            bus.publish(
                "continuation.status", state="desktop_submitted", thread_id=ticket.thread_id
            )
            # Bound post-send observation; preserve the submitted claim on timeout.
            async with asyncio.timeout(DESKTOP_OBSERVATION_SECONDS):
                for _ in range(10):
                    turn = await verified_desktop_turn(self.native, adapter, ticket.thread_id)
                    if turn.get("id") != ticket.turn_id:
                        observed_goal = await adapter.get_goal(ticket.thread_id)
                        if observed_goal is not None:
                            await self.tracker.observe(
                                ticket.account_id,
                                ticket.thread_id,
                                turn,
                                observed_goal,
                                limited=has_verified_limit_turn(turn, observed_goal),
                            )
                            bus.publish("work.observed")
                        break
                    await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            if claimed:
                await self._record(ticket, "uncertain")
            raise
        except Exception:
            if claimed:
                await self._record(ticket, "uncertain")
            bus.publish("continuation.status", state="needs_user", stage="desktop")
        finally:
            unsubscribe()
            try:
                await adapter.aclose()
            finally:
                locks.close()
