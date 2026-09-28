"""Limit-driven conversation continuation, end-to-end with fakes."""

from __future__ import annotations

import pytest

from codex_account_manager.accounts.service import AccountService
from codex_account_manager.adapters.credential_store import FileCredentialStore
from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.auth.transaction import AuthTransaction
from codex_account_manager.continuity.service import ContinuityService
from codex_account_manager.continuity.tracking import WorkTracker
from codex_account_manager.domain.models import ThreadInfo
from codex_account_manager.goals.service import GoalService
from tests.fakes import FakeAppServer, FakeDesktop


def _factory(account_id: str):
    def make(_home: str) -> FakeAppServer:
        return FakeAppServer(account_id=account_id)

    return make


def _thread(tid: str, recency: int, preview: str = "hello") -> ThreadInfo:
    return ThreadInfo(
        id=tid,
        preview=preview,
        cwd="C:/repo",
        path=None,
        model="gpt",
        reasoning_effort=None,
        created_at=1,
        updated_at=recency,
        recency_at=recency,
        status="notLoaded",
    )


def _limited_turn() -> dict:
    return {
        "id": "limited-turn",
        "status": "failed",
        "error": {"codexErrorInfo": "usageLimitExceeded"},
    }


async def _observed_running(thread_id: str, account_id: str = "acc-1") -> None:
    await WorkTracker().observe(
        account_id,
        thread_id,
        {"id": "limited-turn", "status": "inProgress"},
        GoalInfo(thread_id, None, None, False),
    )


async def _seed_two_profiles(migrated_db, accounts: AccountService):
    p1 = await accounts.create_profile("ana")
    p2 = await accounts.create_profile("hesap2")
    for p, acc in ((p1, "acc-1"), (p2, "acc-2")):
        (migrated_db.profiles_dir / p.id / "auth.json").write_bytes(b"{}")
        await accounts.profiles.bind_account(p.id, acc)
    return p1, p2


async def test_tracking_picks_verified_limit_over_newer_unrelated_chat(migrated_db, monkeypatch):
    import codex_account_manager.continuity.service as cs

    fake = FakeAppServer(
        threads=[_thread("old", 100), _thread("new", 999), _thread("mid", 500)],
        turns={"old": _limited_turn(), "new": {"id": "ordinary", "status": "completed"}},
    )
    options = {}

    def factory(_home, **kwargs):
        options.update(kwargs)
        return fake

    monkeypatch.setattr(cs, "CodexAppServer", factory)
    await _observed_running("old")

    await ContinuityService().observe_work()
    assert (await WorkTracker().limited("acc-1"))[0][0] == "old"
    assert options == {"experimental": True}


async def test_tracking_skips_unverified_conversations(migrated_db, monkeypatch):
    import codex_account_manager.continuity.service as cs

    fake = FakeAppServer(
        threads=[_thread("recent", 999)],
        turns={"recent": {"id": "ordinary", "status": "completed"}},
    )
    monkeypatch.setattr(cs, "CodexAppServer", lambda home, **kwargs: fake)

    await ContinuityService().observe_work()
    assert not await WorkTracker().limited("acc-1")


@pytest.mark.parametrize("desktop_owned", [False, True])
async def test_continue_on_limit_carries_active_conversation(
    migrated_db, monkeypatch, desktop_owned
):
    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)

    store = FileCredentialStore(shared_home=migrated_db.shared_codex_home)
    store.write_active_atomic(b"acc-1-auth")

    import codex_account_manager.continuity.service as cs

    # The shared-home adapter reports one active thread with no native goal.
    fake = FakeAppServer(
        account_id="acc-2",
        threads=[_thread("t-live", 999, preview="Refactor the parser")],
        turns={"t-live": _limited_turn()},
        goals={"t-live": None},
    )
    monkeypatch.setattr(cs, "CodexAppServer", lambda home, **kwargs: fake)

    async def verify(_home: str) -> str:
        return "acc-2"

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    service = ContinuityService(accounts=accounts, goals=GoalService())
    service.automation.factory = lambda: fake
    if desktop_owned:
        from codex_account_manager.core.errors import DesktopContinuationRequired

        async def desktop_only(_thread_id):
            raise DesktopContinuationRequired("Continue in Desktop")

        fake.require_headless_compatible = desktop_only
    launched = []
    service.automation.launch_batch = launched.extend
    await _observed_running("t-live", "acc-2")

    result = await service.continue_on_limit("hesap2", transaction=tx)

    assert result.success is True
    # The conversation was resumed on the new profile.
    if desktop_owned:
        assert not fake.resume_calls
        assert len(launched) == 1 and launched[0].desktop
        assert (await service.tracker.visible())[0].turn_status == "awaitingDesktop"
        assert not await service.tracker.limited("acc-2")
    else:
        assert "t-live" in fake.resume_calls
        assert len(launched) == 1 and launched[0].thread_id == "t-live"
    # A preview is not an instruction to create a goal.
    assert fake.set_goal_calls == []
    # New profile's auth is active.
    assert store.read_active() == b"{}"


async def test_continue_on_limit_without_any_thread(migrated_db, monkeypatch):
    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)
    store = FileCredentialStore(shared_home=migrated_db.shared_codex_home)
    store.write_active_atomic(b"acc-1-auth")

    import codex_account_manager.continuity.service as cs

    fake = FakeAppServer(account_id="acc-2", threads=[])  # no threads at all
    monkeypatch.setattr(cs, "CodexAppServer", lambda home, **kwargs: fake)

    async def verify(_home: str) -> str:
        return "acc-2"

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    service = ContinuityService(accounts=accounts, goals=GoalService())

    # Should still switch cleanly even with nothing to carry forward.
    result = await service.continue_on_limit("hesap2", transaction=tx)
    assert result.success is True
    assert store.read_active() == b"{}"


async def test_automatic_work_starts_only_after_committed_handoff(migrated_db, monkeypatch):
    import asyncio

    import codex_account_manager.continuity.service as cs
    from codex_account_manager.continuity.automation import ContinuationSupervisor
    from tests.fakes import ExecutionServer

    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)
    store = FileCredentialStore(shared_home=migrated_db.shared_codex_home)
    store.write_active_atomic(b"previous")
    fake = FakeAppServer(threads=[_thread("thread", 999)], turns={"thread": _limited_turn()})
    monkeypatch.setattr(cs, "CodexAppServer", lambda _home, **kwargs: fake)
    execution = ExecutionServer()
    execution.account_id = "acc-2"
    execution.latest = _limited_turn()
    service = ContinuityService(accounts=accounts)
    service.automation = ContinuationSupervisor(factory=lambda: execution)
    await _observed_running("thread")

    async def cannot_clear(_account_id, _thread_ids):
        raise OSError("checkpoint storage unavailable")

    service.tracker.clear = cannot_clear
    original = execution.run_continuation_turn

    async def after_commit(*args, **kwargs):
        assert (await service.recent_handoffs())[0].success is True
        assert store.read_active() == b"{}"
        return await original(*args, **kwargs)

    execution.run_continuation_turn = after_commit

    async def verify(_home):
        return "acc-2"

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    await service.continue_on_limit("hesap2", transaction=tx)
    await asyncio.gather(*tuple(service.automation.tasks))
    assert len(execution.turn_calls) == 1


async def test_failed_handoff_never_launches_model_work(migrated_db, monkeypatch):
    import pytest

    import codex_account_manager.continuity.service as cs
    from codex_account_manager.continuity.automation import ContinuationSupervisor
    from tests.fakes import ExecutionServer

    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)
    monkeypatch.setattr(
        cs,
        "CodexAppServer",
        lambda _home, **kwargs: FakeAppServer(
            threads=[_thread("thread", 999)], turns={"thread": _limited_turn()}
        ),
    )
    execution = ExecutionServer()
    execution.latest = _limited_turn()
    service = ContinuityService(accounts=accounts)
    service.automation = ContinuationSupervisor(factory=lambda: execution)
    await _observed_running("thread")

    class FailedTransaction:
        async def switch(self, *args, **kwargs):
            raise RuntimeError("switch failed")

    with pytest.raises(RuntimeError, match="switch failed"):
        await service.continue_on_limit("hesap2", transaction=FailedTransaction())
    assert not service.automation.tasks
    assert not execution.turn_calls


async def test_conversation_load_failure_does_not_undo_verified_account_switch(
    migrated_db, monkeypatch
):
    import codex_account_manager.continuity.service as cs
    from codex_account_manager.continuity.automation import ContinuationSupervisor
    from tests.fakes import ExecutionServer

    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)
    store = FileCredentialStore(shared_home=migrated_db.shared_codex_home)
    store.write_active_atomic(b"previous")
    monkeypatch.setattr(
        cs,
        "CodexAppServer",
        lambda _home, **kwargs: FakeAppServer(
            threads=[_thread("thread", 999)], turns={"thread": _limited_turn()}
        ),
    )
    execution = ExecutionServer()
    execution.latest = _limited_turn()
    service = ContinuityService(accounts=accounts)
    service.automation = ContinuationSupervisor(factory=lambda: execution)
    await _observed_running("thread")

    async def cannot_resume(_thread_id):
        raise RuntimeError("Conversation could not be loaded")

    service.resume_conversation = cannot_resume

    async def verify(_home):
        return "acc-2"

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    result = await service.continue_on_limit("hesap2", transaction=tx)
    assert result.success
    assert result.detail == "Conversation could not be loaded"
    assert store.read_active() == b"{}"
    assert not service.automation.tasks
    assert not execution.turn_calls
    handoff = (await service.recent_handoffs())[0]
    assert handoff.success
    assert handoff.detail == result.detail


async def test_history_write_failure_after_commit_does_not_report_switch_failure(migrated_db):
    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)
    store = FileCredentialStore(shared_home=migrated_db.shared_codex_home)
    store.write_active_atomic(b"previous")
    service = ContinuityService(accounts=accounts)
    original_save = service.handoffs.save
    calls = 0

    async def fail_after_commit(record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("history unavailable")
        await original_save(record)

    service.handoffs.save = fail_after_commit

    async def verify(_home):
        return "acc-2"

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    result = await service.handoff("hesap2", transaction=tx)
    assert result.success
    assert store.read_active() == b"{}"
    assert calls == 2


async def test_two_desktop_handoffs_keep_goal_and_follow_new_account(migrated_db, monkeypatch):
    import asyncio
    from dataclasses import replace

    import codex_account_manager.continuity.service as cs
    from codex_account_manager.core.errors import DesktopContinuationRequired

    accounts = AccountService(app_server_factory=_factory("acc-2"))
    await _seed_two_profiles(migrated_db, accounts)
    store = FileCredentialStore(shared_home=migrated_db.shared_codex_home)
    store.write_active_atomic(b"source-auth")
    desktop_thread = replace(_thread("t-live", 999), source="vscode")
    fake = FakeAppServer(account_id="acc-1", threads=[desktop_thread])
    native_goal = GoalInfo("t-live", "Preserve this objective", "active", True, 5000, 100)
    turn = {"id": "first", "status": "inProgress"}
    sends = []

    async def goal(_tid):
        return native_goal

    async def desktop_only(_tid):
        raise DesktopContinuationRequired("Desktop owns this work")

    fake.get_goal = goal
    fake.require_headless_compatible = desktop_only
    monkeypatch.setattr(cs, "CodexAppServer", lambda *_args, **_kwargs: fake)
    service = ContinuityService(accounts=accounts)
    service.automation.factory = lambda: fake

    async def latest(_tid):
        return dict(turn)

    async def send(tid, source_id):
        nonlocal turn
        sends.append((tid, source_id, fake.account_id))
        turn = {"id": f"next-{len(sends)}", "status": "inProgress"}
        return {"threadId": tid}

    service.automation.native.latest_turn = latest
    service.automation.native.send = send
    await service.observe_work()
    for alias, target in [("hesap2", "acc-2"), ("ana", "acc-1")]:
        source_id = turn["id"]
        turn = {
            "id": source_id,
            "status": "failed",
            "error": {"codexErrorInfo": "usageLimitExceeded"},
        }

        async def verify(_home, target=target):
            fake.account_id = target
            return target

        tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
        result = await service.continue_on_limit(alias, transaction=tx)
        assert result.success
        await asyncio.gather(*tuple(service.automation.tasks))
        assert sends[-1] == ("t-live", source_id, target)
        tracked = await service.tracker.visible()
        assert len(tracked) == 1 and tracked[0].turn_status == "inProgress"
        assert not await service.tracker.limited(target)
    assert len(sends) == 2
    assert not fake.resume_calls and not fake.set_goal_calls
    assert native_goal.token_budget == 5000 and native_goal.tokens_used == 100
