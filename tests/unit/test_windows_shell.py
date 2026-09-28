import subprocess
import sys
from pathlib import Path

import pytest

from codex_account_manager.core.windows_shell import APP_USER_MODEL_ID, create_shortcuts

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows shell integration")


def test_shortcuts_match_application_identity_and_use_windowed_launcher(tmp_path):
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    root = tmp_path / "Ã‡alÄ±ÅŸmalar with spaces"
    executable = root / ".venv/Scripts/codex-account-manager.exe"
    icon = root / "packaging/assets/app.ico"
    for path in (executable, icon):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    destinations = (tmp_path / "desktop", tmp_path / "start menu")
    paths = create_shortcuts(root, destinations=destinations)
    assert create_shortcuts(root, destinations=destinations) == paths
    assert len(paths) == 2
    for path in paths:
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )
        shortcut.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
        assert Path(shortcut.GetPath(0)[0]) == executable
        assert shortcut.GetArguments() == ""
        assert Path(shortcut.GetWorkingDirectory()) == root
        assert shortcut.GetIconLocation() == (str(icon), 0)
        properties = propsys.SHGetPropertyStoreFromParsingName(str(path))
        assert properties.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() == APP_USER_MODEL_ID
        assert list(path.parent.iterdir()) == [path]


def test_missing_installation_does_not_create_shortcuts(tmp_path):
    destination = tmp_path / "desktop"
    with pytest.raises(FileNotFoundError, match="bootstrap"):
        create_shortcuts(tmp_path / "missing", destinations=(destination,))
    assert not destination.exists()


def test_process_has_explicit_application_identity():
    script = (
        "from codex_account_manager.core.windows_shell import set_application_identity;"
        "from win32com.shell import shell;"
        "set_application_identity();print(shell.GetCurrentProcessExplicitAppUserModelID())"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == APP_USER_MODEL_ID
