"""Watcher failover behaviour under each switch policy."""

from __future__ import annotations

from datetime import UTC, datetime

from codex_account_manager.continuity.policy import resolve_policy
from codex_account_manager.core.events import bus
from codex_account_manager.domain.models import ProfileHealth
from codex_account_manager.domain.states import QuotaState, SwitchPolicyKind
from codex_account_manager.monitoring.watcher import Watcher


def _health(alias, *, active=False, allowed=True, quota=QuotaState.AVAILABLE, secondary=0.0):
    return ProfileHealth(
        alias=alias,
        profile_id=alias,
        plan_type="plus",
        primary_used_percent=0.0,
        secondary_used_percent=secondary,
        primary_resets_at=None,
        secondary_resets_at=None,
        ordinary_usage_allowed=allowed,
        auth_present=True,
        account_match=True,
        is_active=active,
        quota_state=quota,
        last_checked_at=datetime.now(UTC),
    )


class _FakeContinuity:
    def __init__(self):
        from codex_account_manager.continuity.automation import ContinuationSupervisor

        self.automation = ContinuationSupervisor()
        self.continued: list[str] = []

    async def observe_work(self):
        return {}

    async def continue_on_limit(self, alias: str):
        self.continued.append(alias)


class _StubAccounts:
    def __init__(self, health):
        self._health = health

    async def all_health(self):
        return self._health


async def test_failover_continues_limited_conversation():
    health = [
        _health("ana", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
        _health("hesap2", secondary=5.0),
    ]
    continuity = _FakeContinuity()
    watcher = Watcher(
        accounts=_StubAccounts(health),
        continuity=continuity,
        policy=resolve_policy(SwitchPolicyKind.AVAILABILITY_FAILOVER),
    )
    await watcher.poll_once()
    assert continuity.continued == ["hesap2"]


async def test_confirm_policy_only_suggests():
    health = [
        _health("ana", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
        _health("hesap2", secondary=5.0),
    ]
    continuity = _FakeContinuity()
    suggestions: list[str] = []
    unsubscribe = bus.subscribe(
        "switch.suggested", lambda e: suggestions.append(e.payload["target"])
    )
    try:
        watcher = Watcher(
            accounts=_StubAccounts(health),
            continuity=continuity,
            policy=resolve_policy(SwitchPolicyKind.CONFIRM),
        )
        await watcher.poll_once()
    finally:
        unsubscribe()
    assert continuity.continued == []  # never switches automatically
    assert suggestions == ["hesap2"]


async def test_manual_policy_does_nothing():
    health = [
        _health("ana", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
        _health("hesap2", secondary=5.0),
    ]
    continuity = _FakeContinuity()
    watcher = Watcher(
        accounts=_StubAccounts(health),
        continuity=continuity,
        policy=resolve_policy(SwitchPolicyKind.MANUAL),
    )
    await watcher.poll_once()
    assert continuity.continued == []


async def test_automatic_failure_is_visible_and_redacted():
    class FailingContinuity(_FakeContinuity):
        async def continue_on_limit(self, _alias):
            raise RuntimeError("password=private-value failed")

    health = [
        _health("limited", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
        _health("ready"),
    ]
    events = []
    unsubscribe = bus.subscribe("switch.failed", lambda event: events.append(event))
    try:
        watcher = Watcher(
            accounts=_StubAccounts(health),
            continuity=FailingContinuity(),
            policy=resolve_policy(SwitchPolicyKind.AVAILABILITY_FAILOVER),
        )
        await watcher.poll_once()
    finally:
        unsubscribe()
    assert len(events) == 1
    assert "private-value" not in events[0].payload["detail"]
    assert "failed" in events[0].payload["detail"]


async def test_new_install_defaults_to_automatic_and_sixty_seconds(migrated_db):
    continuity = _FakeContinuity()
    watcher = Watcher(
        accounts=_StubAccounts(
            [
                _health("limited", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
                _health("ready"),
            ]
        ),
        continuity=continuity,
    )
    await watcher.poll_once()
    assert continuity.continued == ["ready"]
    assert watcher.poll_seconds == 60


async def test_saved_manual_mode_and_custom_interval_are_respected(migrated_db):
    from codex_account_manager.storage.repositories import SettingsRepository

    settings = SettingsRepository()
    await settings.set("switch_policy", "manual")
    await settings.set("poll_seconds", "120")
    continuity = _FakeContinuity()
    watcher = Watcher(
        accounts=_StubAccounts(
            [
                _health("limited", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
                _health("ready"),
            ]
        ),
        continuity=continuity,
    )
    await watcher.poll_once()
    assert continuity.continued == []
    assert watcher.poll_seconds == 120


async def test_settings_event_wakes_monitor_without_waiting_old_interval(migrated_db):
    import asyncio

    from codex_account_manager.storage.repositories import SettingsRepository

    seen = asyncio.Queue()

    class Accounts:
        async def all_health(self):
            seen.put_nowait(True)
            return []

    watcher = Watcher(accounts=Accounts(), continuity=_FakeContinuity())
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.wait_for(seen.get(), 2)
        await SettingsRepository().set("poll_seconds", "90")
        bus.publish("monitor.settings_changed")
        await asyncio.wait_for(seen.get(), 2)
        assert watcher.poll_seconds == 90
    finally:
        watcher.stop()
        await asyncio.wait_for(task, 2)


def test_invalid_intervals_have_safe_default():
    from codex_account_manager.monitoring.settings import poll_interval

    for value in (None, "invalid", "", -1, 0, 29, 3601, True):
        assert poll_interval(value) == 60
    for value in (30, "120", 3600):
        assert poll_interval(value) == int(value)


async def test_failed_automatic_switch_uses_backoff_until_another_target(monkeypatch):
    from codex_account_manager.monitoring import watcher as module

    now = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])

    class FailingContinuity(_FakeContinuity):
        def __init__(self):
            super().__init__()
            self.calls = []

        async def continue_on_limit(self, alias):
            self.calls.append(alias)
            raise RuntimeError("Desktop did not start")

    health = [
        _health("limited", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET),
        _health("first"),
    ]
    continuity = FailingContinuity()
    watcher = Watcher(
        accounts=_StubAccounts(health),
        continuity=continuity,
        policy=resolve_policy(SwitchPolicyKind.AVAILABILITY_FAILOVER),
    )
    await watcher.poll_once()
    assert continuity.calls == ["first"]
    now[0] += 60
    await watcher.poll_once()
    assert continuity.calls == ["first"]
    now[0] += 240
    await watcher.poll_once()
    assert continuity.calls == ["first", "first"]
    now[0] += 60
    await watcher.poll_once()
    assert continuity.calls == ["first", "first"]
    health[1] = _health("second")
    await watcher.poll_once()
    assert continuity.calls == ["first", "first", "second"]
