import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from codex_account_manager import updates
from codex_account_manager.core import windows_shell
from codex_account_manager.platform import package, startup


def test_source_process_does_not_use_a_parent_package_identity(monkeypatch):
    monkeypatch.setattr(package, "sys", SimpleNamespace(platform="win32", frozen=False))
    read = Mock(side_effect=AssertionError("A source process must not query package APIs."))
    monkeypatch.setattr(package, "_package_string", read)
    assert package.current_package() is None
    read.assert_not_called()


@pytest.mark.parametrize("inside", [True, False])
def test_frozen_process_requires_its_executable_inside_the_package(tmp_path, monkeypatch, inside):
    root = tmp_path / "installed-package"
    executable = root / "QuotaCrew.exe" if inside else tmp_path / "external/QuotaCrew.exe"
    monkeypatch.setattr(
        package, "sys", SimpleNamespace(platform="win32", frozen=True, executable=str(executable))
    )
    values = {
        "GetCurrentPackageFullName": "QuotaCrew_0.2.1.0_x64__publisher",
        "GetCurrentPackagePath": str(root),
        "GetCurrentPackageFamilyName": "QuotaCrew_publisher",
    }
    monkeypatch.setattr(package, "_package_string", values.__getitem__)
    identity = package.current_package()
    if inside:
        assert identity == package.PackageIdentity(
            values["GetCurrentPackageFullName"], values["GetCurrentPackageFamilyName"], root
        )
    else:
        assert identity is None


def test_msix_launch_keeps_windows_package_identity(monkeypatch):
    monkeypatch.setattr(package, "is_packaged", lambda: True)
    launch = Mock()
    monkeypatch.setattr(windows_shell, "launch_from_explorer", launch)
    assert windows_shell.delegate_gui_launch() is False
    # Neither Explorer delegation nor an explicit unpackaged AUMID is needed.
    shell = Mock()
    monkeypatch.setitem(sys.modules, "win32com.shell", SimpleNamespace(shell=shell))
    windows_shell.set_application_identity()
    launch.assert_not_called()
    shell.SetCurrentProcessExplicitAppUserModelID.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False, None])
def test_msix_startup_uses_startup_task_and_never_registry_fallback(monkeypatch, enabled):
    monkeypatch.setattr(startup, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(package, "is_packaged", lambda: True)
    action = Mock(return_value=True)
    monkeypatch.setattr(package, "startup_action", action)
    registry = Mock(side_effect=AssertionError("MSIX must not edit the Run key."))
    monkeypatch.setitem(
        sys.modules, "winreg", SimpleNamespace(CreateKeyEx=registry, OpenKey=registry)
    )

    def call():
        if enabled is None:
            return startup.is_start_with_windows_enabled()
        if enabled:
            return startup.enable_start_with_windows("ignored")
        return startup.disable_start_with_windows()

    assert call() is True
    action.assert_called_once_with(enabled)
    action.side_effect = ImportError("Missing Windows projection")
    assert call() is False
    registry.assert_not_called()


async def test_msix_cannot_download_or_launch_a_direct_distribution_update(monkeypatch, tmp_path):
    monkeypatch.setattr(package, "is_packaged", lambda: True)
    release = updates.Release("1.0.0", "https://example.com", "https://example.com", 1, "a" * 64)
    opened = Mock()
    launched = Mock()
    monkeypatch.setattr(updates, "_open", opened)
    monkeypatch.setattr(updates, "launch_from_explorer", launched)
    with pytest.raises(updates.UpdateError, match="Microsoft Store"):
        updates.latest_release()
    with pytest.raises(updates.UpdateError, match="Microsoft Store"):
        await updates.download(release)
    with pytest.raises(updates.UpdateError, match="Microsoft Store"):
        updates.begin_install(release, tmp_path / "must-not-run.exe")
    opened.assert_not_called()
    launched.assert_not_called()


def test_store_startup_respects_disabled_by_user_and_releases_com(monkeypatch):
    state = SimpleNamespace(ENABLED=2, DISABLED_BY_USER=3)
    uninit = Mock()
    task = SimpleNamespace(state=state.DISABLED_BY_USER)

    async def get_task(task_id):
        assert task_id == package.STARTUP_TASK_ID
        return task

    async def enable():
        return task.state

    task.request_enable_async = enable
    monkeypatch.setitem(
        sys.modules,
        "winrt.runtime",
        SimpleNamespace(
            ApartmentType=SimpleNamespace(MULTI_THREADED=1),
            init_apartment=Mock(),
            uninit_apartment=uninit,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "winrt.windows.applicationmodel",
        SimpleNamespace(StartupTask=SimpleNamespace(get_async=get_task), StartupTaskState=state),
    )
    assert package.startup_action(True) is False
    assert package.startup_action(None) is False
    assert uninit.call_count == 2
