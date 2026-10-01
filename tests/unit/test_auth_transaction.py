import pytest

from codex_account_manager.adapters.credential_store import FileCredentialStore
from codex_account_manager.auth.transaction import AuthTransaction
from codex_account_manager.core.errors import TransactionError
from codex_account_manager.domain.models import Profile
from codex_account_manager.domain.states import TransactionStage
from tests.fakes import FakeDesktop


def _profile(tmp_paths, account_id="acc-1"):
    home = tmp_paths.profiles_dir / "p1"
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_bytes(b'{"account":"new"}')
    return Profile(id="p1", alias="ana", codex_home=str(home), bound_account_id=account_id)


async def test_successful_switch_commits(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b'{"account":"old"}')
    profile = _profile(tmp_paths, "acc-1")

    async def verify(_home):
        return "acc-1"

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    result = await tx.switch(profile)
    assert result.success
    assert result.final_stage == TransactionStage.COMMIT
    assert store.read_active() == b'{"account":"new"}'


async def test_account_mismatch_rolls_back(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b'{"account":"old"}')
    profile = _profile(tmp_paths, "acc-EXPECTED")

    async def verify(_home):
        return "acc-DIFFERENT"  # mismatch

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    with pytest.raises(TransactionError) as exc:
        await tx.switch(profile)
    assert exc.value.rolled_back is True
    # Old auth restored.
    assert store.read_active() == b'{"account":"old"}'


async def test_unbound_profile_rejected(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    profile = _profile(tmp_paths, account_id=None)
    profile.bound_account_id = None
    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop())
    with pytest.raises(TransactionError):
        await tx.switch(profile)


async def test_crash_during_verify_rolls_back(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b"ORIGINAL")
    profile = _profile(tmp_paths, "acc-1")

    async def verify(_home):
        raise RuntimeError("app server crashed")

    tx = AuthTransaction(credential_store=store, desktop=FakeDesktop(), verify_account=verify)
    with pytest.raises(TransactionError) as exc:
        await tx.switch(profile)
    assert exc.value.rolled_back is True
    assert store.read_active() == b"ORIGINAL"


@pytest.mark.parametrize("still_running", [True, False])
async def test_stop_failure_does_not_repeat_shutdown_or_rewrite_credentials(
    tmp_paths, still_running
):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b"original")
    config = store.shared_home / "config.toml"
    config.write_bytes(b"# original config\n")

    class FailingDesktop(FakeDesktop):
        def stop(self):
            self.stopped += 1
            store.write_active_atomic(b"refreshed by Desktop")
            raise RuntimeError("Desktop shutdown timed out")

        def is_running(self):
            return still_running if self.stopped else True

    async def verify(_home):
        pytest.fail("Must not verify a switch after shutdown failed")

    desktop = FailingDesktop()
    tx = AuthTransaction(credential_store=store, desktop=desktop, verify_account=verify)
    with pytest.raises(TransactionError) as error:
        await tx.switch(_profile(tmp_paths))
    assert error.value.stage == "stop_desktop"
    assert error.value.rolled_back
    assert desktop.stopped == 1
    assert desktop.launched == int(not still_running)
    assert store.read_active() == b"refreshed by Desktop"
    assert config.read_bytes() == b"# original config\n"
    assert not tx.recovery_path.exists()


def test_recovery_before_mutation_preserves_current_credentials(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b"original")
    desktop = FakeDesktop()
    tx = AuthTransaction(credential_store=store, desktop=desktop)
    tx._snapshot()
    store.write_active_atomic(b"refreshed")
    assert tx.recover()
    assert store.read_active() == b"refreshed"
    assert desktop.stopped == 0
    assert not tx.recovery_path.exists()


def test_legacy_recovery_snapshot_still_restores_credentials(tmp_paths):
    import json

    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b"original")
    desktop = FakeDesktop()
    tx = AuthTransaction(credential_store=store, desktop=desktop)
    tx._snapshot()
    payload = json.loads(tx.recovery_path.read_bytes())
    del payload["credentials_may_have_changed"]
    tx.recovery_path.write_text(json.dumps(payload), encoding="utf-8")
    store.write_active_atomic(b"interrupted switch")
    assert tx.recover()
    assert store.read_active() == b"original"
    assert desktop.stopped == 1


async def test_rollback_preserves_credentials_rotated_during_desktop_shutdown(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b"before-shutdown")

    class RotatingDesktop(FakeDesktop):
        def stop(self):
            super().stop()
            if self.stopped == 1:
                store.write_active_atomic(b"rotated-before-exit")

    async def wrong_identity(_home):
        return "wrong-account"

    tx = AuthTransaction(
        credential_store=store, desktop=RotatingDesktop(), verify_account=wrong_identity
    )
    with pytest.raises(TransactionError):
        await tx.switch(_profile(tmp_paths))
    assert store.read_active() == b"rotated-before-exit"


async def test_verified_target_retains_rotated_credentials_for_next_switch(tmp_paths):
    store = FileCredentialStore(shared_home=tmp_paths.shared_codex_home)
    store.write_active_atomic(b"old")
    profile = _profile(tmp_paths)

    async def rotating_verify(_home):
        store.write_active_atomic(b"verified-new-generation")
        return profile.bound_account_id

    tx = AuthTransaction(
        credential_store=store, desktop=FakeDesktop(), verify_account=rotating_verify
    )
    assert (await tx.switch(profile)).success
    assert store.profile_auth_path(profile.codex_home).read_bytes() == b"verified-new-generation"
