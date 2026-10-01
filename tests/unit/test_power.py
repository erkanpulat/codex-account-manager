from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.continuity.tracking import goal_signature
from codex_account_manager.domain.states import QuotaState
from codex_account_manager.monitoring.power import (
    PowerEvidence,
    PowerTarget,
    ShutdownPlan,
    all_accounts_limited,
    work_finished,
)
from tests.unit.test_watcher import _health


def test_shutdown_requires_arming_and_fresh_continuous_evidence():
    plan = ShutdownPlan(60)
    good = PowerEvidence(True, "done", "accounts-a-b")
    plan.observe(good, 0)
    assert plan.remaining(100) is None
    plan.arm(PowerTarget("limits"))
    plan.observe(good, 0)
    assert plan.remaining(10) == 50
    plan.observe(good, 20)
    plan.observe(good, 40)
    plan.observe(good, 60)
    assert plan.remaining(60) == 0
    plan.cancel()
    assert plan.target is None and plan.remaining(60) is None


def test_sleep_stale_evidence_and_changed_accounts_reset_countdown():
    plan = ShutdownPlan(60)
    plan.arm(PowerTarget("limits"))
    plan.observe(PowerEvidence(True, "done", "a"), 0)
    assert plan.remaining(31) is None
    plan.observe(PowerEvidence(True, "done", "a"), 35)
    assert plan.remaining(35) == 60
    plan.observe(PowerEvidence(True, "done", "a-b"), 45)
    assert plan.remaining(45) == 60
    plan.observe(PowerEvidence(False, "network failed"), 50)
    assert plan.remaining(50) is None


@pytest.mark.parametrize("seconds", [0, 59, 86401, 120.5])
def test_countdown_has_bounds(seconds):
    with pytest.raises(ValueError):
        ShutdownPlan(seconds)


@pytest.mark.parametrize("minutes", [120, 180, 1440])
def test_long_countdown_keeps_deadline_with_continuous_verification(minutes):
    plan = ShutdownPlan(minutes * 60)
    plan.arm(PowerTarget("limits"))
    evidence = PowerEvidence(True, "limited", "same-accounts")
    for second in range(0, minutes * 60 + 1, 15):
        plan.observe(evidence, second)
        assert plan.remaining(second) == minutes * 60 - second
    plan.cancel()
    assert plan.remaining(minutes * 60) is None


def test_countdown_can_change_before_arming_but_not_during_a_plan():
    plan = ShutdownPlan()
    plan.set_seconds(420)
    assert plan.seconds == 420
    plan.arm(PowerTarget("limits"))
    plan.observe(PowerEvidence(True, "verified", "accounts"), 10)
    assert plan.remaining(10) == 420
    with pytest.raises(ValueError):
        plan.set_seconds(60)
    plan.cancel()
    plan.set_seconds(60)
    assert plan.seconds == 60


def test_empty_stale_unknown_reauth_and_available_accounts_never_trigger():
    now = datetime.now(UTC)
    good = _health("a", allowed=False, quota=QuotaState.LIMITED_WITH_RESET)
    assert all_accounts_limited([good], now + timedelta(seconds=1))
    assert not all_accounts_limited([], now)
    for changes in [
        {"stale": True},
        {"error": "timeout"},
        {"account_match": None},
        {"reauth_required": True},
        {"ordinary_usage_allowed": None},
        {"auth_present": False},
        {"quota_state": QuotaState.UNKNOWN},
        {"last_checked_at": now - timedelta(seconds=61)},
        {"last_checked_at": now + timedelta(seconds=60)},
        {"last_checked_at": None},
    ]:
        assert not all_accounts_limited([replace(good, **changes)], now), changes
    assert not all_accounts_limited([good, _health("b")], now)


def test_reset_credits_prevent_shutdown():
    from codex_account_manager.domain.models import ResetCredits

    health = _health("a", allowed=False, quota=QuotaState.LIMITED_NO_RESET)
    assert not all_accounts_limited(
        [replace(health, reset_credits=ResetCredits(available_count=1))], datetime.now(UTC)
    )


def test_goal_completion_must_match_original_objective_and_budget():
    goal = GoalInfo("a", "finish task", "active", True, 2000, 100)
    target = PowerTarget("work", "a", goal_signature(goal), "turn-1")
    turn = {"id": "turn-2", "status": "completed"}
    assert work_finished(target, turn, replace(goal, status="complete"))
    for status in ("active", "paused", "usageLimited", "blocked", "budgetLimited"):
        assert not work_finished(target, turn, replace(goal, status=status))
    assert not work_finished(target, turn, replace(goal, status="complete", objective="new"))
    assert not work_finished(
        target, {**turn, "status": "interrupted"}, replace(goal, status="complete")
    )
    assert not work_finished(target, turn, None)


def test_without_goal_only_the_selected_turn_completes():
    target = PowerTarget("work", "a", None, "turn-1")
    goal = GoalInfo("a", None, None, False)
    assert work_finished(target, {"id": "turn-1", "status": "completed"}, goal)
    assert not work_finished(target, {"id": "turn-2", "status": "completed"}, goal)


async def test_power_checks_reject_unknown_active_and_truncated_work(migrated_db, monkeypatch):
    from unittest.mock import AsyncMock

    from codex_account_manager.domain.models import ThreadInfo
    from codex_account_manager.monitoring import power
    from tests.fakes import ExecutionServer

    server = ExecutionServer()
    server.list_threads = AsyncMock(return_value=[])
    monkeypatch.setattr(power, "CodexAppServer", lambda *_a, **_k: server)
    accounts = AsyncMock()
    accounts.all_health.return_value = [
        _health("a", allowed=False, quota=QuotaState.LIMITED_NO_RESET)
    ]
    checks = power.PowerChecks(accounts)
    assert (await checks.check(PowerTarget("limits"))).ready
    server.list_threads.return_value = [None] * 1001
    assert not (await checks.check(PowerTarget("limits"))).ready
    server.list_threads.return_value = [
        ThreadInfo("thread", None, None, None, None, None, None, None, None, "active")
    ]
    checks._turn = AsyncMock(return_value={"id": "turn", "status": "inProgress"})
    assert not (await checks.check(PowerTarget("limits"))).ready
    checks._turn.return_value = None
    assert not (await checks.check(PowerTarget("limits"))).ready
    checks._turn.return_value = {"id": "turn", "status": "completed"}
    server.get_goal = AsyncMock(return_value=None)
    assert not (await checks.check(PowerTarget("limits"))).ready
