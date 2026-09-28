"""Monitor account health and apply the selected switching policy.

Runs in the desktop process and publishes health snapshots to the UI.
"""

from __future__ import annotations

import asyncio
import time

from codex_account_manager.accounts.service import AccountService
from codex_account_manager.continuity.policy import SwitchPolicy, resolve_policy
from codex_account_manager.continuity.service import ContinuityService
from codex_account_manager.core.events import bus
from codex_account_manager.core.logging import get_logger
from codex_account_manager.domain.models import ProfileHealth
from codex_account_manager.domain.states import SwitchPolicyKind
from codex_account_manager.monitoring.settings import (
    DEFAULT_POLICY,
    poll_interval,
)

log = get_logger(__name__)


class Watcher:
    def __init__(
        self,
        *,
        accounts: AccountService | None = None,
        continuity: ContinuityService | None = None,
        policy: SwitchPolicy | None = None,
        poll_seconds: int | None = None,
    ):
        self.accounts = accounts or AccountService()
        self.continuity = continuity or ContinuityService(accounts=self.accounts)
        self.policy = policy or resolve_policy(DEFAULT_POLICY)
        self._load_policy = policy is None
        self.poll_seconds = poll_interval(poll_seconds)
        self._load_interval = poll_seconds is None
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = asyncio.Event()
        self._failed_switch: tuple[str | None, str] | None = None
        self._retry_at = 0.0
        self._retry_delay = 300.0

    def stop(self) -> None:
        def signal() -> None:
            self._stop.set()
            self._wake.set()

        if self._loop:
            self._loop.call_soon_threadsafe(signal)
        else:
            signal()

    async def poll_once(self) -> list[ProfileHealth]:
        """One structured poll. Returns health for all profiles."""
        if self._load_policy:
            from codex_account_manager.storage.repositories import SettingsRepository

            values = await SettingsRepository().all()
            value = values.get("switch_policy", DEFAULT_POLICY)
            if self._load_interval:
                self.poll_seconds = poll_interval(values.get("poll_seconds"))
            try:
                self.policy = resolve_policy(value or DEFAULT_POLICY)
            except ValueError:
                self.policy = resolve_policy(SwitchPolicyKind.MANUAL)
        try:
            await self.continuity.observe_work()
            bus.publish("work.observed")
        except Exception:
            log.warning("Conversation tracking could not be refreshed.")
        health = await self.accounts.all_health()
        bus.publish("health.updated", count=len(health), health=health)
        await self._maybe_failover(health)
        return health

    async def _maybe_failover(self, health: list[ProfileHealth]) -> None:
        automation = getattr(self.continuity, "automation", None)
        if automation is not None and automation.tasks:
            return
        current = next((h for h in health if h.is_active), None)
        decision = self.policy.decide(current, health)
        if not decision.should_switch or decision.target is None:
            self._failed_switch = None
            self._retry_at = 0.0
            self._retry_delay = 300.0
            return
        if decision.requires_confirmation:
            # The policy proposes; a human (GUI/CLI) must confirm. Surface it.
            bus.publish(
                "switch.suggested",
                target=decision.target.alias,
                reason=decision.reason,
            )
            log.info("Switch suggested: %s", decision.reason)
            return
        # Avoid repeatedly restarting Desktop every poll after a failed switch.
        key = (current.profile_id if current else None, decision.target.profile_id)
        if self._failed_switch != key:
            self._failed_switch = None
            self._retry_at = 0.0
            self._retry_delay = 300.0
        if time.monotonic() < self._retry_at:
            return
        # availability_failover: carry the active conversation forward.
        log.info("Policy failover: %s", decision.reason)
        try:
            await self.continuity.continue_on_limit(decision.target.alias)
            self._failed_switch = None
            self._retry_at = 0.0
            self._retry_delay = 300.0
            bus.publish("switch.completed", target=decision.target.alias)
        except Exception as exc:
            self._failed_switch = key
            self._retry_at = time.monotonic() + self._retry_delay
            self._retry_delay = min(self._retry_delay * 2, 1800.0)
            log.warning("Automatic failover failed: %s", exc)
            from codex_account_manager.core.redaction import redact_text

            bus.publish("switch.failed", detail=redact_text(str(exc)))

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()

        def settings_changed(_event) -> None:
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._wake.set)

        unsubscribe = bus.subscribe("monitor.settings_changed", settings_changed)
        unsubscribe_refresh = bus.subscribe("monitor.refresh_requested", settings_changed)
        try:
            while not self._stop.is_set():
                self._wake.clear()
                try:
                    await self.poll_once()
                except Exception:
                    log.exception("Watcher poll failed.")
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    pass
        finally:
            unsubscribe()
            unsubscribe_refresh()
            automation = getattr(self.continuity, "automation", None)
            if automation is not None:
                await automation.stop()
            self._loop = None
