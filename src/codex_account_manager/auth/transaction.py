"""Account switching with a durable recovery snapshot and interprocess exclusion."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from codex_account_manager.adapters.credential_store import FileCredentialStore
from codex_account_manager.adapters.desktop import WindowsDesktopLauncher
from codex_account_manager.adapters.interfaces import DesktopLauncher
from codex_account_manager.core.errors import AccountMismatchError, TransactionError
from codex_account_manager.core.events import bus
from codex_account_manager.core.files import atomic_write
from codex_account_manager.core.logging import get_logger
from codex_account_manager.core.operation_lock import OperationLock
from codex_account_manager.core.paths import paths
from codex_account_manager.core.redaction import redact_text
from codex_account_manager.domain.models import Profile
from codex_account_manager.domain.states import TransactionStage

log = get_logger(__name__)


@dataclass
class SwitchResult:
    success: bool
    final_stage: TransactionStage
    rolled_back: bool = False
    account_id: str | None = None
    detail: str | None = None


@dataclass
class _Journal:
    profile_id: str
    profile_alias: str
    stages: list[dict] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def record(self, stage: TransactionStage, ok: bool = True, detail: str | None = None) -> None:
        self.stages.append(
            {
                "stage": stage.value,
                "ok": ok,
                "detail": redact_text(detail or ""),
                "at": datetime.now(UTC).isoformat(),
            }
        )
        atomic_write(
            paths.data_dir / "switch.journal.json",
            json.dumps(
                {
                    "profile_id": self.profile_id,
                    "profile_alias": self.profile_alias,
                    "started_at": self.started_at,
                    "stages": self.stages,
                }
            ).encode(),
        )

    def clear(self) -> None:
        try:
            (paths.data_dir / "switch.journal.json").unlink(missing_ok=True)
        except OSError:
            log.warning("Could not remove the completed switch journal.")


class AuthTransaction:
    def __init__(
        self,
        *,
        credential_store: FileCredentialStore | None = None,
        desktop: DesktopLauncher | None = None,
        verify_account=None,
        wait_ready_timeout: float = 40.0,
        launch_desktop: bool = True,
    ):
        self.credentials = credential_store or FileCredentialStore()
        self.desktop = desktop if desktop is not None else _default_desktop()
        self._verify_account = verify_account
        self.wait_ready_timeout = wait_ready_timeout
        self.launch_desktop = launch_desktop

    @property
    def recovery_path(self) -> Path:
        return paths.data_dir / "switch.recovery.json"

    def _snapshot(self) -> None:
        payload: dict = {
            "home": str(self.credentials.shared_home.resolve()),
            "desktop_running": self.desktop.is_running(),
            "credentials_may_have_changed": False,
        }
        for name in ("auth.json", "config.toml"):
            source = self.credentials.shared_home / name
            payload[name] = (
                base64.b64encode(source.read_bytes()).decode() if source.exists() else None
            )
        atomic_write(self.recovery_path, json.dumps(payload).encode())

    def _arm_recovery(self) -> None:
        payload = json.loads(self.recovery_path.read_bytes())
        payload["credentials_may_have_changed"] = True
        atomic_write(self.recovery_path, json.dumps(payload).encode())

    def _restore(self) -> None:
        payload = json.loads(self.recovery_path.read_bytes())
        if payload.get("home") != str(self.credentials.shared_home.resolve()):
            raise TransactionError(
                "Recovery snapshot belongs to a different Codex home.", stage="rollback"
            )
        # Validate the entire snapshot before making any changes.
        decoded = {
            name: base64.b64decode(payload[name], validate=True)
            if payload[name] is not None
            else None
            for name in ("auth.json", "config.toml")
        }
        if payload.get("credentials_may_have_changed") is False:
            if (
                payload.get("desktop_running")
                and self.launch_desktop
                and not self.desktop.is_running()
            ):
                self.desktop.launch()
            self.recovery_path.unlink()
            return
        self.desktop.stop()
        self.credentials.restore_active(decoded["auth.json"])
        config = self.credentials.shared_home / "config.toml"
        if decoded["config.toml"] is None:
            config.unlink(missing_ok=True)
        else:
            atomic_write(config, decoded["config.toml"])
        if payload.get("desktop_running") and self.launch_desktop:
            self.desktop.launch()
        self.recovery_path.unlink()

    def recover(self) -> bool:
        """Restore an interrupted switch before starting the GUI or another switch."""
        with OperationLock(paths.data_dir / "account-operation.lock"):
            if not self.recovery_path.exists():
                return False
            self._restore()
            (paths.data_dir / "switch.journal.json").unlink(missing_ok=True)
            return True

    async def switch(
        self, target: Profile, *, after_switch: Callable[[], Awaitable[None]] | None = None
    ) -> SwitchResult:
        with OperationLock(paths.data_dir / "account-operation.lock"):
            if self.recovery_path.exists():
                self._restore()
            return await self._switch_locked(target, after_switch=after_switch)

    async def _switch_locked(
        self, target: Profile, *, after_switch: Callable[[], Awaitable[None]] | None
    ) -> SwitchResult:
        if not target.bound_account_id:
            raise TransactionError(
                f"Profile '{target.alias}' is not bound to an account.", stage="prepare"
            )
        source = self.credentials.profile_auth_path(target.codex_home)
        if not source.is_file():
            raise TransactionError(
                f"Profile '{target.alias}' has no auth.json to activate.", stage="prepare"
            )
        if self._verify_account is None:
            from codex_account_manager.accounts.service import AccountService

            service = AccountService()
            active_id = await service._active_account_id_safe()
            for profile in await service.list_profiles():
                if active_id and profile.bound_account_id == active_id:
                    self.credentials.sync_active_to_profile(profile.codex_home)
                    break
            account_id = await self._verify(Path(target.codex_home))
            if account_id != target.bound_account_id:
                raise AccountMismatchError("Profile credentials no longer match its bound account.")
        new_auth = source.read_bytes()
        if not new_auth:
            raise TransactionError("Profile credentials are empty.", stage="prepare")
        journal = _Journal(profile_id=target.id, profile_alias=target.alias)
        current_stage = TransactionStage.PREPARE
        snapshot_written = False

        def stage(value: TransactionStage) -> None:
            nonlocal current_stage
            current_stage = value
            journal.record(value)
            bus.publish("switch.stage", stage=value.value, ok=True, alias=target.alias)

        try:
            stage(TransactionStage.PREPARE)
            stage(TransactionStage.BACKUP_ACTIVE_AUTH)
            self._snapshot()
            snapshot_written = True
            stage(TransactionStage.STOP_DESKTOP)
            self.desktop.stop()
            self._arm_recovery()
            self.credentials.ensure_file_auth_config()
            stage(TransactionStage.ATOMIC_REPLACE)
            self.credentials.write_active_atomic(new_auth)
            stage(TransactionStage.VERIFY_ACCOUNT)
            account_id = await self._verify(self.credentials.shared_home)
            if account_id != target.bound_account_id:
                raise AccountMismatchError(
                    "Activated auth does not match the profile's bound account."
                )
            if self.launch_desktop:
                stage(TransactionStage.START_DESKTOP)
                self.desktop.launch()
                stage(TransactionStage.WAIT_READY)
                if not await self.desktop.wait_ready(self.wait_ready_timeout):
                    raise TransactionError("Desktop readiness timed out.", stage="wait_ready")
            if after_switch is not None:
                stage(TransactionStage.RESUME_THREAD)
                await after_switch()
            stage(TransactionStage.COMMIT)
            # Deleting the snapshot is the commit point; no fallible work follows.
            self.recovery_path.unlink()
            snapshot_written = False
            journal.clear()
            return SwitchResult(True, TransactionStage.COMMIT, account_id=account_id)
        except (Exception, asyncio.CancelledError) as exc:
            detail = redact_text(str(exc)) or "Account switch cancelled."
            rolled_back = False
            if snapshot_written:
                try:
                    self._restore()
                    rolled_back = True
                except Exception:
                    log.exception("Rollback incomplete; recovery snapshot retained.")
            try:
                journal.record(TransactionStage.ROLLBACK, False, detail)
            except OSError:
                log.warning("Could not write rollback journal.")
            bus.publish(
                "switch.failed",
                alias=target.alias,
                stage=current_stage.value,
                rolled_back=rolled_back,
                detail=detail,
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise TransactionError(
                detail, stage=current_stage.value, rolled_back=rolled_back
            ) from exc

    async def _verify(self, codex_home: Path) -> str | None:
        if self._verify_account is not None:
            return await self._verify_account(str(codex_home))
        from codex_account_manager.accounts.service import AccountService

        snapshot = await AccountService().read_snapshot(codex_home)
        return snapshot.account_id


def _default_desktop() -> DesktopLauncher:
    import sys

    return WindowsDesktopLauncher() if sys.platform == "win32" else _NullDesktop()


class _NullDesktop:
    def stop(self) -> None: ...
    def launch(self) -> None: ...
    def is_running(self) -> bool:
        return False

    async def wait_ready(self, timeout: float = 30.0) -> bool:
        return True
