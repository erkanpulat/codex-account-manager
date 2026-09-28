from codex_account_manager.core.single_instance import SingleInstance


def test_second_instance_is_blocked(tmp_paths):
    name = "Local\\CodexAccountManagerTest"
    first = SingleInstance(name)
    assert first.acquire() is True
    second = SingleInstance(name)
    assert second.acquire() is False
    first.release()
    # After release, a new instance can acquire.
    third = SingleInstance(name)
    assert third.acquire() is True
    third.release()
