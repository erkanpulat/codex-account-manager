from unittest.mock import Mock

import pytest

from codex_account_manager.platform import editors


def test_editor_discovery_uses_known_locations_without_process_scans(tmp_path, monkeypatch):
    monkeypatch.setattr(editors.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "programs"))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    executable = tmp_path / "local/Programs/Microsoft VS Code/Code.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert editors.installed_editors() == {"VS Code": executable}
    monkeypatch.setattr(editors.sys, "platform", "linux")
    assert editors.installed_editors() == {}


def test_project_open_passes_one_literal_folder_argument_without_shell(tmp_path, monkeypatch):
    folder = tmp_path / "project & spaces"
    folder.mkdir()
    executable = tmp_path / "Code.exe"
    monkeypatch.setattr(editors, "installed_editors", lambda: {"VS Code": executable})
    spawn = Mock()
    monkeypatch.setattr(editors.subprocess, "Popen", spawn)
    editors.open_project("VS Code", str(folder))
    assert spawn.call_args.args[0] == [str(executable), "--new-window", str(folder.resolve())]
    assert spawn.call_args.kwargs["shell"] is False


@pytest.mark.parametrize(
    "folder", ["", "relative", "--install-extension=anything", "//remote/share", "missing"]
)
def test_invalid_workspace_never_launches_editor(tmp_path, monkeypatch, folder):
    monkeypatch.setattr(editors, "installed_editors", lambda: {"VS Code": tmp_path / "Code.exe"})
    spawn = Mock()
    monkeypatch.setattr(editors.subprocess, "Popen", spawn)
    with pytest.raises(ValueError):
        editors.open_project("VS Code", folder)
    spawn.assert_not_called()


def test_unknown_editor_is_not_a_command(tmp_path, monkeypatch):
    monkeypatch.setattr(editors, "installed_editors", lambda: {})
    with pytest.raises(ValueError):
        editors.open_project("arbitrary.exe", str(tmp_path))
