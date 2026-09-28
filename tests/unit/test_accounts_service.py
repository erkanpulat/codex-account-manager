import asyncio
import subprocess
import sys

import pytest

from codex_account_manager.accounts.service import AccountService
from tests.fakes import FakeAppServer


def _factory(account_id="acc-1", **kw):
    def make(_home):
        return FakeAppServer(account_id=account_id, **kw)

    return make


async def test_create_and_list_profile(migrated_db):
    svc = AccountService(app_server_factory=_factory())
    profile = await svc.create_profile("ana")
    assert profile.alias == "ana"
    profiles = await svc.list_profiles()
    assert [p.alias for p in profiles] == ["ana"]
    # New profile uses file auth config.
    config = (migrated_db.profiles_dir / profile.id / "config.toml").read_text(encoding="utf-8")
    assert 'cli_auth_credentials_store = "file"' in config


async def test_bind_and_health_match(migrated_db):
    svc = AccountService(app_server_factory=_factory("acc-1"))
    profile = await svc.create_profile("ana")
    # Write a fake auth so auth_present is true.
    (migrated_db.profiles_dir / profile.id / "auth.json").write_bytes(b"{}")
    account_id = await svc.bind_current_account("ana")
    assert account_id == "acc-1"
    health = await svc.health("ana")
    assert health.account_match is True
    assert health.auth_present is True
    assert health.plan_type == "plus"


async def test_all_health_reports_every_profile(migrated_db):
    svc = AccountService(app_server_factory=_factory("acc-1"))
    await svc.create_profile("ana")
    await svc.create_profile("hesap2")
    health = await svc.all_health()
    assert {h.alias for h in health} == {"ana", "hesap2"}


async def test_health_survives_app_server_error(migrated_db):
    svc = AccountService(app_server_factory=_factory("acc-1", fail_on={"read_account"}))
    await svc.create_profile("ana")
    health = await svc.health("ana")
    assert health.error is not None
    assert health.plan_type is None


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout", "cancel"])
async def test_login_subprocess_lifecycle(migrated_db, monkeypatch, outcome):
    from codex_account_manager.codex import runtime

    svc = AccountService(app_server_factory=_factory())
    profile = await svc.create_profile("login-test")
    scripts = {
        "success": "import os,pathlib;pathlib.Path(os.environ['CODEX_HOME'],'auth.json').write_text('{}')",
        "failure": "raise SystemExit(7)",
        "timeout": "import time;time.sleep(30)",
        "cancel": "import time;time.sleep(30)",
    }

    def command(*args):
        assert args == ("login",)
        return [sys.executable, "-c", scripts[outcome]]

    monkeypatch.setattr(runtime, "codex_command", command)
    spawn = asyncio.create_subprocess_exec
    processes = []
    started = asyncio.Event()

    async def capture_process(*args, **kwargs):
        assert kwargs["env"]["CODEX_HOME"] == profile.codex_home
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = await spawn(*args, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_process)
    if outcome == "timeout":
        wait_for = asyncio.wait_for

        async def short_timeout(awaitable, timeout):
            assert timeout == 600
            return await wait_for(awaitable, timeout=0.05)

        monkeypatch.setattr(asyncio, "wait_for", short_timeout)

    if outcome == "success":
        assert await svc.login_profile(profile.alias) == "acc-1"
        assert (await svc.list_profiles())[0].bound_account_id == "acc-1"
    elif outcome == "cancel":
        task = asyncio.create_task(svc.login_profile(profile.alias))
        await asyncio.wait_for(started.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        message = "sign-in failed" if outcome == "failure" else "timed out"
        with pytest.raises(ValueError, match=message):
            await svc.login_profile(profile.alias)
    assert len(processes) == 1
    assert processes[0].returncode is not None
    from codex_account_manager.core.operation_lock import OperationLock

    with OperationLock(migrated_db.data_dir / "account-operation.lock"):
        pass
    if outcome != "success":
        assert (await svc.list_profiles())[0].bound_account_id is None
