"""AccountService — the structured API the CLI, GUI and watcher all use.

Returns typed snapshots (``AccountSnapshot``, ``ProfileHealth``) instead of
rendered tables. The monitoring watcher uses the same snapshots as the UI.

The service is constructed with an App Server *factory* so tests can inject a
fake adapter without a real Codex install.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from codex_account_manager.adapters.app_server import CodexAppServer
from codex_account_manager.adapters.credential_store import FileCredentialStore
from codex_account_manager.adapters.interfaces import AppServerAdapter
from codex_account_manager.codex.quota import evaluate_quota
from codex_account_manager.core.errors import AccountMismatchError, ProfileNotFoundError
from codex_account_manager.core.files import restrict_access
from codex_account_manager.core.logging import get_logger
from codex_account_manager.core.operation_lock import OperationLock
from codex_account_manager.core.paths import paths
from codex_account_manager.core.redaction import redact_text
from codex_account_manager.domain.models import AccountSnapshot, Profile, ProfileHealth
from codex_account_manager.domain.states import QuotaState
from codex_account_manager.storage.repositories import ProfileRepository

log = get_logger(__name__)

AppServerFactory = Callable[[str], AppServerAdapter]

_PROFILE_CONFIG = 'cli_auth_credentials_store = "file"\n'
#: Upper bound on concurrent App Server reads to keep the machine responsive.
_MAX_CONCURRENT_READS = 4


def _default_factory(codex_home: str) -> AppServerAdapter:
    return CodexAppServer(codex_home)


async def _safe_aclose(adapter: AppServerAdapter) -> None:
    try:
        await adapter.aclose()
    except Exception:
        pass


class AccountService:
    def __init__(
        self,
        profiles: ProfileRepository | None = None,
        *,
        app_server_factory: AppServerFactory | None = None,
        credential_store: FileCredentialStore | None = None,
    ):
        self.profiles = profiles or ProfileRepository()
        self._factory = app_server_factory or _default_factory
        self.credentials = credential_store or FileCredentialStore()

    # Profile lifecycle
    async def list_profiles(self) -> list[Profile]:
        return await self.profiles.list()

    async def create_profile(self, alias: str) -> Profile:
        alias = _validate_alias(alias)
        profile_id = str(uuid4())
        codex_home = paths.profiles_dir / profile_id
        paths.profiles_dir.mkdir(parents=True, exist_ok=True)
        codex_home.mkdir(parents=True, exist_ok=False)
        try:
            restrict_access(codex_home)
            (codex_home / "config.toml").write_text(_PROFILE_CONFIG, encoding="utf-8")
            profile = Profile(id=profile_id, alias=alias, codex_home=str(codex_home))
            await self.profiles.create(profile)
        except sqlite3.IntegrityError as exc:
            shutil.rmtree(codex_home, ignore_errors=True)
            raise ValueError("A profile with this name already exists.") from exc
        except Exception:
            shutil.rmtree(codex_home, ignore_errors=True)
            raise
        return profile

    async def rename_profile(self, alias: str, new_alias: str) -> None:
        profile = await self._require(alias)
        try:
            await self.profiles.rename(profile.id, _validate_alias(new_alias))
        except sqlite3.IntegrityError as exc:
            raise ValueError("A profile with this name already exists.") from exc

    async def remove_profile(self, alias: str, *, delete_files: bool = True) -> None:
        profile = await self._require(alias)
        with OperationLock(paths.data_dir / "account-operation.lock"):
            home = Path(profile.codex_home)
            managed = paths.profiles_dir.resolve()
            resolved = home.resolve()
            if delete_files and (
                home.is_symlink()
                or resolved.parent != managed
                or resolved == paths.shared_codex_home.resolve()
            ):
                raise ValueError("Refusing to delete a directory outside managed profiles.")
            if delete_files and home.exists():
                shutil.rmtree(home)
            await self.profiles.delete(profile.id)

    async def login_profile(self, alias: str) -> str:
        import subprocess
        import sys

        from codex_account_manager.codex.runtime import codex_command, profile_environment

        profile = await self._require(alias)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_CONSOLE
        with OperationLock(paths.data_dir / "account-operation.lock"):
            process = await asyncio.create_subprocess_exec(
                *codex_command("login"),
                env=profile_environment(profile.codex_home),
                creationflags=creationflags,
            )
            try:
                code = await asyncio.wait_for(process.wait(), timeout=600)
            except TimeoutError:
                raise ValueError(
                    "Codex sign-in timed out after 10 minutes. Try signing in again."
                ) from None
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            if code != 0:
                log.warning("Codex sign-in exited with code %s", code)
                raise ValueError(
                    "Codex sign-in failed. Check Codex in Settings > System check, then try again."
                )
            restrict_access(Path(profile.codex_home) / "auth.json")
            return await self._bind_current_account(alias)

    async def bind_current_account(self, alias: str) -> str:
        with OperationLock(paths.data_dir / "account-operation.lock"):
            return await self._bind_current_account(alias)

    async def _bind_current_account(self, alias: str) -> str:
        profile = await self._require(alias)
        snapshot = await self.read_snapshot(profile.codex_home)
        if not snapshot.account_id:
            raise AccountMismatchError("Could not read an account id to bind.")
        try:
            await self.profiles.bind_account(profile.id, snapshot.account_id)
        except sqlite3.IntegrityError as exc:
            raise ValueError("This account is already bound to another profile.") from exc
        return snapshot.account_id

    # Reads
    async def read_snapshot(self, codex_home: str | Path) -> AccountSnapshot:
        adapter = self._factory(str(codex_home))
        try:
            await adapter.start()
            return await adapter.read_account()
        finally:
            # Shield cleanup so a cancellation (e.g. app shutdown) still tears
            # the subprocess down instead of leaking its transport.
            await asyncio.shield(_safe_aclose(adapter))

    async def health(self, alias: str) -> ProfileHealth:
        profile = await self._require(alias)
        active_id = await self._active_account_id_safe()
        return await self._health_for(profile, active_account_id=active_id)

    async def all_health(self) -> list[ProfileHealth]:
        """Structured health for every profile, read concurrently.

        Profiles are read in parallel with bounded concurrency so refreshing a
        dozen accounts stays fast without spawning an unbounded number of App
        Server processes at once.
        """
        profiles = await self.profiles.list()
        if not profiles:
            return []
        active_id = await self._active_account_id_safe()
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_READS)

        async def _bounded(profile: Profile) -> ProfileHealth:
            async with semaphore:
                return await self._health_for(profile, active_account_id=active_id)

        return list(await asyncio.gather(*(_bounded(p) for p in profiles)))

    async def _health_for(
        self, profile: Profile, *, active_account_id: str | None
    ) -> ProfileHealth:
        auth_present = self.credentials.profile_auth_path(profile.codex_home).exists()
        try:
            snapshot = await self.read_snapshot(profile.codex_home)
            decision = evaluate_quota(snapshot)
            match = (
                None
                if not profile.bound_account_id
                else profile.bound_account_id == snapshot.account_id
            )
            is_active = bool(
                profile.bound_account_id and profile.bound_account_id == active_account_id
            )
            return ProfileHealth(
                alias=profile.alias,
                profile_id=profile.id,
                plan_type=snapshot.plan_type,
                reset_credits=snapshot.reset_credits if match is True else None,
                primary_used_percent=snapshot.primary_used_percent,
                secondary_used_percent=snapshot.secondary_used_percent,
                primary_resets_at=snapshot.primary_resets_at,
                secondary_resets_at=snapshot.secondary_resets_at,
                ordinary_usage_allowed=snapshot.ordinary_usage_allowed,
                auth_present=auth_present,
                account_match=match,
                is_active=is_active,
                quota_state=decision.state,
                last_checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            return ProfileHealth(
                alias=profile.alias,
                profile_id=profile.id,
                plan_type=None,
                primary_used_percent=None,
                secondary_used_percent=None,
                primary_resets_at=None,
                secondary_resets_at=None,
                ordinary_usage_allowed=None,
                auth_present=auth_present,
                account_match=None,
                is_active=bool(
                    profile.bound_account_id and profile.bound_account_id == active_account_id
                ),
                quota_state=QuotaState.UNKNOWN,
                last_checked_at=datetime.now(UTC),
                error=redact_text(str(exc)),
            )

    async def active_account_id(self) -> str | None:
        """Account id currently active in the shared home."""
        snapshot = await self.read_snapshot(paths.shared_codex_home)
        return snapshot.account_id

    async def _active_account_id_safe(self) -> str | None:
        try:
            return await self.active_account_id()
        except Exception:
            return None

    async def resolve_active_alias(self) -> str | None:
        active_id = await self._active_account_id_safe()
        if not active_id:
            return None
        for profile in await self.profiles.list():
            if profile.bound_account_id == active_id:
                return profile.alias
        return None

    async def _require(self, alias: str) -> Profile:
        profile = await self.profiles.get_by_alias(alias)
        if not profile:
            raise ProfileNotFoundError(f"Profile not found: {alias}")
        return profile


def _validate_alias(alias: str) -> str:
    alias = alias.strip()
    if not alias or len(alias) > 64 or any(ord(char) < 32 or ord(char) == 127 for char in alias):
        raise ValueError("Use a profile name of 1–64 characters without control characters.")
    return alias
