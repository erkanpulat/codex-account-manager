"""Windows application identity and shortcuts for a source installation."""

from __future__ import annotations

import sys
from pathlib import Path

APP_USER_MODEL_ID = "CodexAccountManager.Desktop"


def set_application_identity() -> None:
    if sys.platform == "win32":
        from win32com.shell import shell

        shell.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def create_shortcuts(
    project_root: Path, *, destinations: tuple[Path, ...] | None = None
) -> list[Path]:
    if sys.platform != "win32":
        raise OSError("Desktop shortcuts are supported on Windows only.")

    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell, shellcon

    root = project_root.resolve()
    executable = root / ".venv" / "Scripts" / "codex-account-manager.exe"
    icon = root / "packaging" / "assets" / "app.ico"
    for required in (executable, icon):
        if not required.is_file():
            raise FileNotFoundError(f"Run scripts/bootstrap.ps1 first. Missing: {required}")
    if destinations is None:
        destinations = tuple(
            Path(shell.SHGetFolderPath(0, folder, None, 0))
            for folder in (shellcon.CSIDL_DESKTOPDIRECTORY, shellcon.CSIDL_PROGRAMS)
        )
    created = []
    for directory in destinations:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "Codex Account Manager.lnk"
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )
        shortcut.SetPath(str(executable))
        shortcut.SetArguments("")
        shortcut.SetWorkingDirectory(str(root))
        shortcut.SetIconLocation(str(icon), 0)
        shortcut.SetDescription("Codex Account Manager")
        shortcut.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 1)
        properties = propsys.SHGetPropertyStoreFromParsingName(
            str(path), None, shellcon.GPS_READWRITE, propsys.IID_IPropertyStore
        )
        properties.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_USER_MODEL_ID))
        properties.Commit()
        created.append(path)
    return created


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create desktop and Start Menu shortcuts.")
    parser.add_argument("project_root", type=Path)
    for shortcut_path in create_shortcuts(parser.parse_args().project_root):
        print(f"Shortcut created: {shortcut_path}")
