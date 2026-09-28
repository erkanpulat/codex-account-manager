"""Conversation tracking, account handoffs, and post-switch continuation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from codex_account_manager.accounts.service import AccountService
from codex_account_manager.adapters.app_server import CodexAppServer
from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.adapters.native_desktop import verified_desktop_turn
from codex_account_manager.auth.transaction import AuthTransaction, SwitchResult
from codex_account_manager.continuity.automation import (
    ContinuationSupervisor,
    ContinuationTicket,
    has_verified_limit_turn,
)
from codex_account_manager.continuity.tracking import WorkTracker
from codex_account_manager.core.errors import AppServerError, DesktopContinuationRequired
from codex_account_manager.core.events import bus
from codex_account_manager.core.logging import get_logger
from codex_account_manager.core.paths import paths
from codex_account_manager.core.redaction import redact_text
from codex_account_manager.domain.models import HandoffRecord, ThreadRecord
from codex_account_manager.domain.states import GoalState, HandoffReason
from codex_account_manager.goals.service import GoalService
from codex_account_manager.storage.repositories import (
    EventRepository,
    HandoffRepository,
    ProfileRepository,
    ThreadRepository,
)

log = get_logger(__name__)

OBSERVATION_TIMEOUT = 30.0
THREAD_CHECK_TIMEOUT = 2.0
THREAD_SCAN_TIMEOUT = 10.0
THREAD_CHECK_CONCURRENCY = 4


class ContinuityService:
    def __init__(
        self,
        *,
        accounts: AccountService | None = None,
        goals: GoalService | None = None,
        threads: ThreadRepository | None = None,
        handoffs: HandoffRepository | None = None,
        events: EventRepository | None = None,
        profiles: ProfileRepository | None = None,
    ):
        self.accounts = accounts or AccountService()
        self.goals = goals or GoalService()
        self.threads = threads or ThreadRepository()
        self.handoffs = handoffs or HandoffRepository()
        self.events = events or EventRepository()
        self.profiles = profiles or ProfileRepository()
        self.automation = ContinuationSupervisor()
        self.tracker = WorkTracker()

    # Thread tracking
    async def sync_threads(self) -> list[ThreadRecord]:
        """Read threads from the App Server and persist lightweight records."""
        adapter = CodexAppServer(paths.shared_codex_home)
        try:
            await adapter.start()
            infos = await adapter.list_threads()
        finally:
            await adapter.aclose()

        def timestamp(value: int | None) -> datetime:
            try:
                return datetime.fromtimestamp(value or 0, UTC)
            except (ValueError, OverflowError, OSError):
                return datetime.fromtimestamp(0, UTC)

        records: list[ThreadRecord] = []
        for info in infos:
            if not info.id:
                continue

            record = ThreadRecord(
                id=info.id,
                cwd=info.cwd,
                workspace=info.cwd,
                preview=info.preview,
                title=info.title,
                source=info.source,
                project_id=info.project_id,
                model_provider=info.model_provider,
                created_at=timestamp(info.created_at),
                updated_at=timestamp(info.recency_at or info.updated_at or info.created_at),
            )
            records.append(record)
        await self.threads.replace_listed(records)
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    async def read_native_goal(self, thread_id: str) -> GoalInfo | None:
        adapter = CodexAppServer(paths.shared_codex_home)
        try:
            await adapter.start()
            return await adapter.get_goal(thread_id)
        finally:
            await adapter.aclose()

    async def observe_work(self) -> str | None:
        """Refresh running and interrupted work before evaluating account failover."""
        bus.publish("work.observation_status", state="checking")
        try:
            async with asyncio.timeout(OBSERVATION_TIMEOUT):
                return await self._observe_work()
        except TimeoutError:
            bus.publish("work.observation_status", state="timed_out")
            raise
        except Exception:
            bus.publish("work.observation_status", state="failed")
            raise

    async def _observe_work(self) -> str | None:
        adapter = CodexAppServer(paths.shared_codex_home, experimental=True)
        try:
            await adapter.start()
            account_id = (await adapter.read_account()).account_id
            if not account_id:
                bus.publish("work.observation_status", state="signed_out")
                return None
            infos = await adapter.list_threads(max_items=30, include_subagents=False)
            candidates = sorted(
                (i for i in infos if i.id and not (i.source or "").startswith("subAgent")),
                key=lambda i: i.recency_at or i.updated_at or 0,
                reverse=True,
            )
            tracked = await self.tracker.ids(account_id)
            selected = list(dict.fromkeys([*tracked, *(i.id for i in candidates[:20])]))
            desktop_ids = {i.id for i in candidates if i.source == "vscode"}
            for thread_id in tracked:
                saved_thread = await self.threads.get(thread_id)
                if saved_thread and saved_thread.source == "vscode":
                    desktop_ids.add(thread_id)
            checked = 0
            unavailable = 0
            semaphore = asyncio.Semaphore(THREAD_CHECK_CONCURRENCY)

            async def inspect(thread_id: str) -> None:
                nonlocal checked, unavailable
                async with semaphore:
                    try:
                        async with asyncio.timeout(THREAD_CHECK_TIMEOUT):
                            turn: dict | None
                            if thread_id in desktop_ids:
                                turn = await verified_desktop_turn(
                                    self.automation.native, adapter, thread_id
                                )
                            else:
                                turn = await adapter.observed_turn(thread_id)
                            goal = await adapter.get_goal(thread_id) if turn else None
                            if turn and goal is None:
                                raise AppServerError("Observed goal could not be verified.")
                            await self.tracker.observe(
                                account_id,
                                thread_id,
                                turn,
                                goal,
                                limited=has_verified_limit_turn(turn, goal),
                            )
                            checked += 1
                            bus.publish("work.observed")
                    except Exception:
                        unavailable += 1
                        log.warning("Could not verify an observed conversation.")

            try:
                async with asyncio.timeout(THREAD_SCAN_TIMEOUT):
                    async with asyncio.TaskGroup() as group:
                        for thread_id in selected:
                            group.create_task(inspect(thread_id))
            except TimeoutError:
                unavailable = len(selected) - checked
            bus.publish(
                "work.observation_status",
                state="partial" if unavailable else "ready",
                checked=checked,
                unavailable=unavailable,
                checked_at=datetime.now().strftime("%H:%M:%S"),
            )
            return account_id
        finally:
            await adapter.aclose()

    # Account switch commits before conversation loading and goal reconciliation.
    async def handoff(
        self,
        target_alias: str,
        *,
        reason: HandoffReason = HandoffReason.MANUAL,
        thread_id: str | None = None,
        transaction: AuthTransaction | None = None,
    ) -> SwitchResult:
        target = await self.profiles.get_by_alias(target_alias)
        if not target:
            from codex_account_manager.core.errors import ProfileNotFoundError

            raise ProfileNotFoundError(f"Profile not found: {target_alias}")

        from_alias = await self.accounts.resolve_active_alias()
        from_profile = await self.profiles.get_by_alias(from_alias) if from_alias else None

        handoff = HandoffRecord(
            thread_id=thread_id,
            from_profile_id=from_profile.id if from_profile else None,
            to_profile_id=target.id,
            reason=reason,
        )
        await self.handoffs.save(handoff)
        await self.events.append(
            "handoff.started",
            thread_id=thread_id,
            profile_id=target.id,
            payload={"reason": reason.value, "from": from_alias, "to": target_alias},
        )

        if thread_id:
            await self.goals.mark_status(thread_id, GoalState.SWITCHING)

        tx = transaction or AuthTransaction()
        try:
            result = await tx.switch(target)
        except (Exception, asyncio.CancelledError) as exc:
            handoff.finished_at = datetime.now(UTC)
            handoff.success = False
            handoff.rolled_back = getattr(exc, "rolled_back", False)
            handoff.final_stage = getattr(exc, "stage", None)
            handoff.detail = redact_text(str(exc))
            await self.handoffs.save(handoff)
            await self.events.append(
                "handoff.failed", thread_id=thread_id, payload={"detail": redact_text(str(exc))}
            )
            if thread_id:
                await self.goals.mark_status(thread_id, GoalState.NEEDS_USER)
            raise

        handoff.finished_at = datetime.now(UTC)
        handoff.success = True
        handoff.final_stage = result.final_stage.value
        try:
            await self.handoffs.save(handoff)
            await self.events.append("handoff.completed", thread_id=thread_id, profile_id=target.id)
        except Exception:
            log.warning("Verified account switch committed but its history could not be saved.")
        if thread_id:
            try:
                await self.resume_conversation(thread_id)
            except Exception as exc:
                detail = redact_text(str(exc))
                result.detail = detail
                handoff.detail = detail
                try:
                    await self.handoffs.save(handoff)
                    await self.events.append(
                        "thread.resume_failed", thread_id=thread_id, payload={"detail": detail}
                    )
                    await self.goals.mark_status(thread_id, GoalState.NEEDS_USER)
                except Exception:
                    log.warning("Could not record the conversation load failure.")
                bus.publish("continuation.status", state="needs_user")
        return result

    async def continue_on_limit(
        self, target_alias: str, *, transaction: AuthTransaction | None = None
    ) -> SwitchResult:
        """Commit the account handoff before starting any verified interrupted work."""
        if self.automation.tasks:
            raise AppServerError("An automatic continuation is still running.")
        account_id = None
        try:
            account_id = await self.observe_work()
        except (Exception, asyncio.CancelledError) as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            log.warning("Could not refresh conversations before account handoff: %s", exc)
        saved = await self.tracker.limited(account_id) if account_id else []
        tickets = []
        preparation_failed = False
        desktop_threads: list[str] = []
        desktop_tickets: list[ContinuationTicket] = []
        for thread_id, turn_id, signature in saved:
            try:
                ticket = await self.automation.prepare(thread_id)
                if ticket and ticket.turn_id == turn_id and ticket.goal_signature == signature:
                    tickets.append(ticket)
            except DesktopContinuationRequired:
                desktop_threads.append(thread_id)
                desktop_tickets.append(
                    ContinuationTicket(thread_id, turn_id, goal_signature=signature, desktop=True)
                )
            except Exception:
                preparation_failed = True
        selected_thread = tickets[0].thread_id if tickets else None
        result = await self.handoff(
            target_alias,
            reason=HandoffReason.USAGE_LIMITED,
            thread_id=selected_thread,
            transaction=transaction,
        )
        if account_id:
            try:
                await self.tracker.clear(account_id, [ticket.thread_id for ticket in tickets])
            except Exception:
                log.warning("Account switch committed; observed work could not be cleared.")
        ready_desktop: list[ContinuationTicket] = []
        if desktop_threads and account_id:
            try:
                target = await self.profiles.get_by_alias(target_alias)
                if not target or not target.bound_account_id:
                    raise AppServerError("The target account identity could not be verified.")
                await self.tracker.await_desktop(
                    account_id, target.bound_account_id, desktop_threads
                )
                bus.publish("work.observed")
                ready_desktop = desktop_tickets
            except Exception:
                log.warning("Account switch committed; Desktop follow-up could not be saved.")
                bus.publish("continuation.status", state="needs_user", stage="journal")
        tickets = ready_desktop + (tickets if result.detail is None else [])
        if tickets:
            try:
                target = await self.profiles.get_by_alias(target_alias)
                if not target or not target.bound_account_id:
                    raise AppServerError("The target account identity could not be verified.")
                self.automation.launch_batch(
                    [
                        ContinuationTicket(
                            ticket.thread_id,
                            ticket.turn_id,
                            target.bound_account_id,
                            ticket.goal_signature,
                            desktop=ticket.desktop,
                        )
                        for ticket in tickets
                    ]
                )
            except Exception:
                log.warning("Account switch committed; automatic continuation could not start.")
                bus.publish("continuation.status", state="needs_user", stage="connection")
        elif not desktop_threads and await self.automation.enabled():
            bus.publish(
                "continuation.status", state="needs_user" if preparation_failed else "skipped"
            )
        return result

    async def resume_conversation(self, thread_id: str) -> None:
        await self.goals.mark_status(thread_id, GoalState.RESUMING)
        adapter = CodexAppServer(paths.shared_codex_home)
        try:
            await adapter.start()
            await adapter.resume_thread(thread_id)
            await self.events.append("thread.resumed", thread_id=thread_id)
            result = await self.goals.reconcile_after_resume(thread_id, adapter)
            if result.action == "blocked":
                raise AppServerError(result.detail)
            await self.events.append(
                "goal.reconciled", thread_id=thread_id, payload={"action": result.action}
            )
        finally:
            await adapter.aclose()

    # Read models for the GUI/CLI
    async def recent_handoffs(self, limit: int = 20) -> list[HandoffRecord]:
        return await self.handoffs.recent(limit)
