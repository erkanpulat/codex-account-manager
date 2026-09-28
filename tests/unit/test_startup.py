from types import SimpleNamespace

from codex_account_manager.platform import startup


def test_startup_registration_is_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(startup, "sys", SimpleNamespace(platform="linux"))
    assert startup.enable_start_with_windows("example-command") is False
    assert startup.disable_start_with_windows() is False
    assert startup.is_start_with_windows_enabled() is False
