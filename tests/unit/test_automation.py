import asyncio
from dataclasses import replace

import pytest

from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.continuity.automation import (
    ContinuationSupervisor,
    goal_allows_continuation,
)
from codex_account_manager.core.events import bus
from codex_account_manager.domain.states import GoalState
from codex_account_manager.storage.database import connect
from codex_account_manager.storage.repositories import SettingsRepository
from tests.fakes import ExecutionServer


def goal(status="active", *, budget=1000, used=100):
    return GoalInfo("thread", "Finish the requested task", status, True, budget, used)


async def prepared(supervisor):
    ticket = await supervisor.prepare("thread")
    assert ticket is not None
    return replace(ticket, account_id="acc-1")


@pytest.mark.parametrize("status", ["paused", "blocked", "complete", "budgetLimited", "unknown"])
def test_native_goal_states_are_never_automatically_reactivated(status):
    assert not goal_allows_continuation(goal(status))


@pytest.mark.parametrize(
    "budget,used", [(100, 100), (100, 101), (-1, 0), (True, 0), (100, -1), (100, True)]
)
def test_goal_budget_is_not_reset_or_ignored(budget, used):
    assert not goal_allows_continuation(goal(budget=budget, used=used))


@pytest.mark.parametrize(
    "status,error",
    [
        ("interrupted", None),
        ("inProgress", None),
        ("completed", None),
        ("failed", "sessionBudgetExceeded"),
        ("failed", "other"),
        ("failed", "rateLimitExceeded"),
    ],
)
async def test_unverified_or_user_interrupted_work_is_not_selected(migrated_db, status, error):
    server = ExecutionServer()
    server.latest = {"id": "last", "status": status, "error": {"codexErrorInfo": error}}
    supervisor = ContinuationSupervisor(factory=lambda: server)
    assert await supervisor.prepare("thread") is None
    assert server.closed


async def test_usage_limit_without_goal_continues_exactly_one_turn(migrated_db):
    server = ExecutionServer()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    await supervisor.run(ticket)
    assert len(server.turn_calls) == 1
    assert server.resume_calls == ["thread"]
    assert server.closed
    async with connect() as db:
        assert await (await db.execute("SELECT status FROM continuation_attempts")).fetchall() == [
            ("completed",)
        ]


async def test_limit_during_owned_continuation_remains_eligible_for_next_handoff(migrated_db):
    class LimitedAgain(ExecutionServer):
        async def run_continuation_turn(self, *args, **kwargs):
            turn = await super().run_continuation_turn(*args, **kwargs)
            self.latest = {
                **turn,
                "status": "failed",
                "error": {"codexErrorInfo": "usageLimitExceeded"},
            }
            return self.latest

    server = LimitedAgain()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    await supervisor.run(await prepared(supervisor))
    pending = await supervisor.tracker.limited("acc-1")
    assert len(pending) == 1
    assert pending[0][1] == "1"
    next_ticket = await supervisor.prepare("thread")
    assert next_ticket is not None and next_ticket.turn_id == "1"
    assert not await supervisor.tracker.limited("acc-other")


async def test_active_goal_continues_until_complete_without_resetting_budget(migrated_db):
    server = ExecutionServer()
    server.native = goal("usageLimited", used=200)
    server.after_turn = [goal(used=300), goal("complete", used=400)]
    supervisor = ContinuationSupervisor(factory=lambda: server)
    await supervisor.run(await prepared(supervisor))
    assert len(server.turn_calls) == 2
    assert server.reactivations == [goal("usageLimited", used=200)]
    assert server.native.token_budget == 1000
    assert server.native.tokens_used == 400


async def test_goal_budget_exhausted_after_first_turn_stops_loop(migrated_db):
    server = ExecutionServer()
    server.native = goal()
    server.after_turn = [goal("budgetLimited", used=1000)]
    supervisor = ContinuationSupervisor(factory=lambda: server)
    await supervisor.run(await prepared(supervisor))
    assert len(server.turn_calls) == 1
    assert server.reactivations == []


async def test_changed_goal_after_handoff_does_not_receive_old_continuation(migrated_db):
    server = ExecutionServer()
    server.native = goal()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    server.native = replace(server.native, objective="A different user request")
    await supervisor.run(ticket)
    assert not server.turn_calls


async def test_batch_continues_each_saved_thread_in_order(migrated_db):
    server = ExecutionServer()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    seen = []

    async def run(saved):
        seen.append(saved.thread_id)

    supervisor.run = run
    supervisor.launch_batch([ticket, replace(ticket, thread_id="second")])
    await asyncio.gather(*tuple(supervisor.tasks))
    assert seen == ["thread", "second"]


async def test_unknown_goal_after_handoff_reports_goal_stage_without_sending(migrated_db):
    server = ExecutionServer()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    server.native = None
    events = []
    unsubscribe = bus.subscribe("continuation.status", lambda event: events.append(event.payload))
    try:
        await supervisor.run(ticket)
    finally:
        unsubscribe()
    assert not server.turn_calls
    assert events[-1] == {"state": "needs_user", "stage": "goal"}


async def test_unknown_goal_during_preparation_is_not_reported_as_no_interruption(migrated_db):
    from codex_account_manager.core.errors import AppServerError

    server = ExecutionServer()
    server.native = None
    supervisor = ContinuationSupervisor(factory=lambda: server)
    with pytest.raises(AppServerError, match="verify the goal"):
        await supervisor.prepare("thread")
    assert not server.turn_calls
    assert server.closed


async def test_ambiguous_delivery_is_not_resent_even_by_new_supervisor(migrated_db):
    server = ExecutionServer()
    server.fail_send = True
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    await supervisor.run(ticket)
    await ContinuationSupervisor(factory=lambda: server).run(ticket)
    assert len(server.turn_calls) == 1
    async with connect() as db:
        assert await (await db.execute("SELECT status FROM continuation_attempts")).fetchall() == [
            ("uncertain",)
        ]


@pytest.mark.parametrize("change", ["account", "turn", "pause", "clear", "disabled"])
async def test_changes_during_handoff_prevent_sending(migrated_db, change):
    server = ExecutionServer()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    if change == "account":
        server.account_id = "different"
    elif change == "turn":
        server.latest = {"id": "user-new-turn", "status": "completed"}
    elif change == "disabled":
        await SettingsRepository().set("auto_continue", "false")
    else:
        await supervisor.goals.set_objective("thread", "Task")
        if change == "pause":
            await supervisor.goals.mark_status("thread", GoalState.PAUSED)
        else:
            await supervisor.goals.user_clear("thread")
    await supervisor.run(ticket)
    assert not server.turn_calls


async def test_disable_signal_cancels_running_work_and_releases_locks(migrated_db):
    from codex_account_manager.core.operation_lock import OperationLock

    server = ExecutionServer()
    server.wait = True
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    task = asyncio.create_task(supervisor.run(ticket))
    await asyncio.wait_for(server.started_turn.wait(), 2)
    bus.publish("continuation.stop")
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert server.closed
    with OperationLock(migrated_db.data_dir / "account-operation.lock"):
        pass


async def test_two_workers_cannot_send_the_same_turn(migrated_db):
    server = ExecutionServer()
    server.wait = True
    first = ContinuationSupervisor(factory=lambda: server)
    second = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(first)
    task = asyncio.create_task(first.run(ticket))
    try:
        await asyncio.wait_for(server.started_turn.wait(), 2)
        await second.run(ticket)
        assert len(server.turn_calls) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_account_lock_is_held_until_execution_connection_closes(migrated_db):
    from codex_account_manager.core.errors import TransactionError
    from codex_account_manager.core.operation_lock import OperationLock

    server = ExecutionServer()
    supervisor = ContinuationSupervisor(factory=lambda: server)
    ticket = await prepared(supervisor)
    closed_with_lock = []

    async def close():
        with pytest.raises(TransactionError):
            with OperationLock(migrated_db.data_dir / "account-operation.lock"):
                pass
        closed_with_lock.append(True)

    server.aclose = close
    await supervisor.run(ticket)
    assert closed_with_lock == [True]
    with OperationLock(migrated_db.data_dir / "account-operation.lock"):
        pass


async def test_desktop_preparation_never_claims_or_resumes_conversation(migrated_db):
    from codex_account_manager.core.errors import DesktopContinuationRequired

    server = ExecutionServer()

    async def desktop_only(_thread_id):
        raise DesktopContinuationRequired("Continue in Desktop")

    server.require_headless_compatible = desktop_only
    supervisor = ContinuationSupervisor(factory=lambda: server)
    with pytest.raises(DesktopContinuationRequired):
        await supervisor.prepare("thread")
    assert not server.resume_calls
    assert not server.turn_calls
    assert server.closed
