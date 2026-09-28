from dataclasses import replace

from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.continuity.service import ContinuityService
from codex_account_manager.continuity.tracking import WorkTracker
from tests.fakes import FakeAppServer
from tests.integration.test_limit_continuation import _limited_turn, _thread


async def test_running_work_survives_restart_and_remains_tracked_outside_recent_twenty(
    migrated_db, monkeypatch
):
    import codex_account_manager.continuity.service as module

    server = FakeAppServer(
        account_id="account-a",
        threads=[_thread("working", 100)],
        turns={"working": {"id": "limited-turn", "status": "inProgress"}},
    )
    monkeypatch.setattr(module, "CodexAppServer", lambda _, **kwargs: server)
    await ContinuityService().observe_work()
    assert await WorkTracker().ids("account-a") == ["working"]
    server._threads.extend(_thread(str(i), 1000 + i) for i in range(25))
    server._turns["working"] = _limited_turn()
    restarted = ContinuityService()
    await restarted.observe_work()
    assert (await restarted.tracker.limited("account-a"))[0][1] == "limited-turn"


async def test_new_turn_invalidates_saved_interruption(migrated_db):
    tracker = WorkTracker()
    absent = GoalInfo("thread", None, None, False)
    await tracker.observe(
        "account-a", "thread", {"id": "limited-turn", "status": "inProgress"}, absent
    )
    await tracker.observe("account-a", "thread", _limited_turn(), absent, limited=True)
    assert await tracker.limited("account-a")
    await tracker.observe("account-a", "thread", {"id": "user", "status": "completed"}, absent)
    assert not await tracker.limited("account-a")


async def test_unverifiable_goal_keeps_checkpoint_for_later_revalidation(migrated_db, monkeypatch):
    import codex_account_manager.continuity.service as module

    tracker = WorkTracker()
    absent = GoalInfo("thread", None, None, False)
    await tracker.observe(
        "account-a", "thread", {"id": "limited-turn", "status": "inProgress"}, absent
    )
    await tracker.observe("account-a", "thread", _limited_turn(), absent, limited=True)
    server = FakeAppServer(
        account_id="account-a", threads=[_thread("thread", 100)], turns={"thread": _limited_turn()}
    )
    server.get_goal = lambda _thread_id: _unknown_goal()
    monkeypatch.setattr(module, "CodexAppServer", lambda _, **kwargs: server)
    await ContinuityService().observe_work()
    assert (await tracker.limited("account-a"))[0][0] == "thread"


async def _unknown_goal():
    return None


async def test_multiple_interrupted_conversations_survive_restart_without_content(migrated_db):
    from codex_account_manager.storage.database import connect

    tracker = WorkTracker()
    for tid in ("one", "two"):
        goal = GoalInfo(tid, "private objective", "usageLimited", True, 500, 10)
        await tracker.observe(
            "account-a", tid, {"id": "limited-turn", "status": "inProgress"}, goal
        )
        await tracker.observe("account-a", tid, _limited_turn(), goal, limited=True)
    assert {row[0] for row in await WorkTracker().limited("account-a")} == {"one", "two"}
    async with connect() as db:
        rows = await (await db.execute("SELECT goal_fingerprint FROM observed_work")).fetchall()
    assert all("private objective" not in row[0] for row in rows)
    display = await tracker.visible()
    assert len(display) == 2
    assert all(work.goal_status == "usageLimited" and work.goal_present for work in display)


async def test_historical_limit_without_observed_running_turn_is_not_selected(migrated_db):
    tracker = WorkTracker()
    absent = GoalInfo("old", None, None, False)
    await tracker.observe("account-a", "old", _limited_turn(), absent, limited=True)
    assert not await tracker.limited("account-a")


async def test_saved_work_cannot_cross_account_or_survive_new_goal(migrated_db):
    tracker = WorkTracker()
    old_goal = GoalInfo("thread", "Original", "active", True, 500, 10)
    new_goal = GoalInfo("thread", "Replacement", "active", True, 500, 10)
    await tracker.observe(
        "account-a", "thread", {"id": "limited-turn", "status": "inProgress"}, old_goal
    )
    await tracker.observe("account-b", "thread", _limited_turn(), old_goal, limited=True)
    assert not await tracker.limited("account-b")
    await tracker.observe("account-a", "thread", _limited_turn(), new_goal, limited=True)
    assert not await tracker.limited("account-a")


async def test_consumed_interruption_is_not_reused(migrated_db):
    tracker = WorkTracker()
    absent = GoalInfo("thread", None, None, False)
    await tracker.observe(
        "account-a", "thread", {"id": "limited-turn", "status": "inProgress"}, absent
    )
    await tracker.observe("account-a", "thread", _limited_turn(), absent, limited=True)
    assert await tracker.limited("account-a")
    await tracker.clear("account-a", ["thread"])
    assert not await tracker.limited("account-a")


async def test_desktop_handoff_keeps_tracking_under_new_account_without_reusing_old_limit(
    migrated_db,
):
    tracker = WorkTracker()
    absent = GoalInfo("thread", None, None, False)
    await tracker.observe(
        "old-account", "thread", {"id": "limited-turn", "status": "inProgress"}, absent
    )
    await tracker.observe("old-account", "thread", _limited_turn(), absent, limited=True)
    await tracker.await_desktop("old-account", "new-account", ["thread"])
    pending = await tracker.visible()
    assert pending[0].turn_status == "awaitingDesktop"
    assert await tracker.ids("new-account") == ["thread"]
    assert not await tracker.limited("new-account")
    assert not await tracker.limited("old-account")
    await tracker.observe("new-account", "thread", _limited_turn(), absent, limited=True)
    assert (await tracker.visible())[0].turn_status == "awaitingDesktop"
    await tracker.observe("new-account", "thread", {"id": "next", "status": "inProgress"}, absent)
    await tracker.observe(
        "new-account", "thread", {**_limited_turn(), "id": "next"}, absent, limited=True
    )
    assert (await tracker.limited("new-account"))[0][1] == "next"


async def test_desktop_followup_cannot_transfer_another_accounts_work(migrated_db):
    tracker = WorkTracker()
    absent = GoalInfo("thread", None, None, False)
    await tracker.observe("owner", "thread", {"id": "limited-turn", "status": "inProgress"}, absent)
    await tracker.observe("owner", "thread", _limited_turn(), absent, limited=True)
    await tracker.await_desktop("unrelated", "target", ["thread"])
    assert await tracker.limited("owner")
    assert not await tracker.ids("target")


async def test_stalled_conversation_does_not_hide_running_work(migrated_db, monkeypatch):
    import asyncio

    import codex_account_manager.continuity.service as module

    server = FakeAppServer(
        account_id="account-a", threads=[_thread("slow", 200), _thread("live", 100)]
    )
    cancelled = asyncio.Event()

    async def observed(thread_id):
        if thread_id == "slow":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return {"id": "live-turn", "status": "inProgress"}

    server.observed_turn = observed
    monkeypatch.setattr(module, "CodexAppServer", lambda _, **kwargs: server)
    monkeypatch.setattr(module, "THREAD_CHECK_TIMEOUT", 0.1)
    statuses = []
    unsubscribe = module.bus.subscribe(
        "work.observation_status", lambda event: statuses.append(event.payload)
    )
    try:
        assert await ContinuityService().observe_work() == "account-a"
    finally:
        unsubscribe()
    assert cancelled.is_set()
    assert await WorkTracker().ids("account-a") == ["live"]
    assert statuses[-1]["state"] == "partial"
    assert statuses[-1]["checked"] == 1
    assert statuses[-1]["unavailable"] == 1


async def test_scan_deadline_preserves_results_and_cancels_pending_reads(migrated_db, monkeypatch):
    import asyncio

    import codex_account_manager.continuity.service as module

    server = FakeAppServer(
        account_id="account-a", threads=[_thread("live", 200), _thread("slow", 100)]
    )
    pending = set()

    async def observed(thread_id):
        if thread_id == "slow":
            pending.add(thread_id)
            try:
                await asyncio.Event().wait()
            finally:
                pending.remove(thread_id)
        return {"id": "live-turn", "status": "inProgress"}

    server.observed_turn = observed
    monkeypatch.setattr(module, "CodexAppServer", lambda _, **kwargs: server)
    monkeypatch.setattr(module, "THREAD_SCAN_TIMEOUT", 0.1)
    monkeypatch.setattr(module, "THREAD_CHECK_TIMEOUT", 10)
    assert await ContinuityService().observe_work() == "account-a"
    assert not pending
    assert await WorkTracker().ids("account-a") == ["live"]


async def test_desktop_limit_keeps_running_checkpoint_when_summary_omits_error_code(
    migrated_db, monkeypatch
):
    from unittest.mock import AsyncMock

    import codex_account_manager.continuity.service as module

    thread = replace(_thread("desktop", 100), source="vscode")
    server = FakeAppServer(account_id="owner", threads=[thread])
    monkeypatch.setattr(module, "CodexAppServer", lambda _, **kwargs: server)
    service = ContinuityService()
    running = {"id": "same-turn", "status": "inProgress"}
    service.automation.native.latest_turn = AsyncMock(return_value=running)
    await service.observe_work()
    assert await service.tracker.ids("owner") == ["desktop"]
    server._turns["desktop"] = {**_limited_turn(), "id": "same-turn"}
    service.automation.native.latest_turn.return_value = {
        "id": "same-turn",
        "status": "failed",
        "error": {"message": "Localized quota error"},
    }
    await service.observe_work()
    assert (await service.tracker.limited("owner"))[0][1] == "same-turn"
