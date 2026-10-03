import asyncio
import base64
import subprocess
import sys
from unittest.mock import Mock

import pytest

from codex_account_manager.adapters.credential_store import FileCredentialStore, ProfileAuthSession
from codex_account_manager.auth.transaction import AuthTransaction
from codex_account_manager.core import protection
from codex_account_manager.core.errors import AccountRecoveryRequired, OperationBusyError
from codex_account_manager.storage.migrations import migrate
from tests.fakes import FakeDesktop

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Native Windows DPAPI and process jobs"
)


@pytest.fixture
def profile_home(tmp_paths):
    home = tmp_paths.profiles_dir / "synthetic-profile"
    home.mkdir()
    return home


def test_dpapi_roundtrip_tamper_wrong_purpose_and_no_plaintext_fallback(monkeypatch):
    import win32crypt

    data = b"synthetic private token for security tests only"
    blob = protection.protect(data, b"test-purpose")
    assert blob.startswith(protection.MAGIC) and data not in blob
    assert protection.unprotect(blob, b"test-purpose") == data
    for ciphertext, purpose in (
        (blob[:-1] + bytes([blob[-1] ^ 1]), b"test-purpose"),
        (blob, b"wrong-purpose"),
        (data, b"test-purpose"),
    ):
        with pytest.raises(protection.CredentialProtectionError):
            protection.unprotect(ciphertext, purpose)
    failing = Mock(side_effect=RuntimeError(data.decode()))
    monkeypatch.setattr(win32crypt, "CryptProtectData", failing)
    with pytest.raises(protection.CredentialProtectionError) as failure:
        protection.protect(data, b"test-purpose")
    assert data.decode() not in str(failure.value)
    assert failing.call_args.args[-1] == 1  # current-user scope, UI forbidden


def test_idle_migration_session_refresh_and_logout(profile_home):
    raw = profile_home / "auth.json"
    vault = profile_home / "auth.dpapi"
    raw.write_bytes(b"original-synthetic-token")
    store = FileCredentialStore()
    store.protect_profiles()
    assert not raw.exists() and vault.exists()
    assert b"original-synthetic-token" not in vault.read_bytes()
    with store.profile_session(profile_home):
        assert raw.read_bytes() == b"original-synthetic-token"
        raw.write_bytes(b"rotated-synthetic-token")
    assert not raw.exists()
    assert store.read_profile(profile_home) == b"rotated-synthetic-token"
    with store.profile_session(profile_home):
        raw.unlink()  # official client revoked/removed the login
    assert not raw.exists() and not vault.exists()


def test_failed_protection_retains_only_usable_original(profile_home, monkeypatch):
    raw = profile_home / "auth.json"
    raw.write_bytes(b"synthetic-token")
    monkeypatch.setattr(
        protection,
        "protect",
        Mock(side_effect=protection.CredentialProtectionError("Test failure")),
    )
    with pytest.raises(protection.CredentialProtectionError):
        FileCredentialStore().protect_profiles()
    assert raw.read_bytes() == b"synthetic-token"
    assert not (profile_home / "auth.dpapi").exists()


def test_second_session_cannot_reseal_first_process_credentials(profile_home):
    raw = profile_home / "auth.json"
    raw.write_bytes(b"initial")
    with ProfileAuthSession(profile_home):
        raw.write_bytes(b"refresh in progress")
        second = ProfileAuthSession(profile_home)
        with pytest.raises(OperationBusyError):
            second.__enter__()
        second.__exit__(None, None, None)
        FileCredentialStore().protect_profiles()  # busy profile must be skipped
        assert raw.read_bytes() == b"refresh in progress"
    assert not raw.exists()
    assert FileCredentialStore().read_profile(profile_home) == b"refresh in progress"


def test_reauthentication_keeps_old_login_on_cancel_and_can_replace_unreadable_vault(profile_home):
    vault = profile_home / "auth.dpapi"
    vault.write_bytes(b"synthetic broken or foreign-user vault")
    original = vault.read_bytes()
    with ProfileAuthSession(profile_home, signing_in=True):
        assert not (profile_home / "auth.json").exists()
    assert vault.read_bytes() == original
    with ProfileAuthSession(profile_home, signing_in=True):
        (profile_home / "auth.json").write_bytes(b"new synthetic login")
    assert FileCredentialStore().read_profile(profile_home) == b"new synthetic login"


def test_leftover_refreshed_token_after_crash_becomes_durable(profile_home):
    store = FileCredentialStore()
    raw = profile_home / "auth.json"
    raw.write_bytes(b"older")
    store.protect_profiles()
    # Emulate the disk state following an abrupt exit during a refresh.
    raw.write_bytes(b"newer")
    store.protect_profiles()
    assert not raw.exists()
    assert store.read_profile(profile_home) == b"newer"


def test_recovery_snapshot_is_encrypted_and_corruption_cannot_replace_active_auth(tmp_paths):
    store = FileCredentialStore()
    original = b"synthetic-original-login"
    store.write_active_atomic(original)
    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop())
    tx._snapshot()
    tx._arm_recovery()
    blob = tx.recovery_path.read_bytes()
    assert original not in blob and base64.b64encode(original) not in blob
    assert blob.startswith(protection.MAGIC)
    tx.recovery_path.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
    store.write_active_atomic(b"current")
    with pytest.raises(protection.CredentialProtectionError):
        tx.recover()
    assert store.read_active() == b"current"
    assert tx.recovery_path.exists()


async def test_missing_database_with_encrypted_signin_requires_recovery(tmp_paths, profile_home):
    (profile_home / "auth.dpapi").write_bytes(protection.protect(b"synthetic", b"test"))
    with pytest.raises(AccountRecoveryRequired):
        await migrate()
    assert not tmp_paths.db_path.exists()


@pytest.mark.parametrize("initialization_error", [False, True])
async def test_real_child_refresh_is_sealed_after_close_or_initialization_failure(
    profile_home, monkeypatch, initialization_error
):
    from codex_account_manager.adapters import app_server

    raw = profile_home / "auth.json"
    raw.write_bytes(b"before")
    program = """
import json, os, pathlib, sys
auth = pathlib.Path(os.environ['CODEX_HOME']) / 'auth.json'
assert auth.read_bytes() == b'before'
for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    auth.write_bytes(b'after-refresh')
    response = {'id': request['id'], 'result': {'userAgent': 'synthetic-test'}}
    if os.environ.get('QUOTACREW_TEST_INIT_ERROR') == '1':
        response = {'id': request['id'], 'error': {'code': -1, 'message': 'synthetic failure'}}
    print(json.dumps(response), flush=True)
"""
    monkeypatch.setenv("QUOTACREW_TEST_INIT_ERROR", "1" if initialization_error else "0")
    monkeypatch.setattr(
        app_server, "codex_command", lambda *_: [sys.executable, "-u", "-c", program]
    )
    server = app_server.CodexAppServer(profile_home)
    if initialization_error:
        with pytest.raises(app_server.AppServerError):
            await server.start()
    else:
        assert (await server.start()).user_agent == "synthetic-test"
        assert raw.exists()
        await server.aclose()
    assert server._proc is None
    assert not raw.exists()
    assert FileCredentialStore().read_profile(profile_home) == b"after-refresh"


async def test_parent_crash_terminates_only_its_owned_child(tmp_path):
    import psutil

    pid_file = tmp_path / "owned-child.pid"
    program = """
import os, pathlib, subprocess, sys
from codex_account_manager.core.child_process import ChildProcessLifetime
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(45)'], creationflags=subprocess.CREATE_NO_WINDOW)
pathlib.Path(sys.argv[1]).write_text(str(child.pid))
job = ChildProcessLifetime()
try:
    job.attach(child.pid)
except BaseException:
    child.kill()
    child.wait()
    raise
os._exit(0)
"""
    parent = await asyncio.create_subprocess_exec(
        sys.executable, "-c", program, str(pid_file), creationflags=subprocess.CREATE_NO_WINDOW
    )
    try:
        assert await asyncio.wait_for(parent.wait(), 10) == 0
        child_pid = int(pid_file.read_text())
        for _ in range(40):
            if not psutil.pid_exists(child_pid):
                break
            await asyncio.sleep(0.05)
        assert not psutil.pid_exists(child_pid)
    finally:
        if parent.returncode is None:
            parent.kill()
            await parent.wait()
