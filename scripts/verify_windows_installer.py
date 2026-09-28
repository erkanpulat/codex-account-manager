"""Verify install/uninstall on a disposable GitHub-hosted Windows runner only."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if (
        sys.platform != "win32"
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise SystemExit(
            "Installer verification requires a disposable GitHub-hosted Windows runner."
        )

    import winreg

    import win32com.client

    def startup_command() -> str | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
            ) as key:
                return winreg.QueryValueEx(key, "CodexAccountManager")[0]
        except FileNotFoundError:
            return None

    installers = list(Path("installer/Output").glob("CodexAccountManager-Setup-*.exe"))
    if len(installers) != 1:
        raise RuntimeError("Expected exactly one freshly built installer.")
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop_link = Path(shell.SpecialFolders("Desktop")) / "Codex Account Manager.lnk"
    menu_dir = Path(shell.SpecialFolders("Programs")) / "Codex Account Manager"
    menu_link = menu_dir / "Codex Account Manager.lnk"
    data_dir = Path(os.environ["LOCALAPPDATA"]) / "CodexAccountManager"
    if (
        data_dir.exists()
        or desktop_link.exists()
        or menu_dir.exists()
        or startup_command() is not None
    ):
        raise RuntimeError(
            "Refusing to modify an existing application installation or data directory."
        )
    data_dir.mkdir()
    sentinel = data_dir / "installer-preservation-test.txt"
    sentinel.write_bytes(b"Synthetic user data must survive installation and removal.\n")
    expected = sentinel.read_bytes()
    with tempfile.TemporaryDirectory(
        prefix="account-manager-install-", dir=os.environ["RUNNER_TEMP"]
    ) as temporary:
        destination = Path(temporary) / "application"
        flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
        try:
            subprocess.run(
                [
                    str(installers[0].resolve()),
                    *flags,
                    f"/DIR={destination}",
                    "/LANG=english",
                    f"/LOG={Path(temporary) / 'install.log'}",
                    "/TASKS=desktopicon,startupicon",
                ],
                check=True,
                timeout=180,
            )
            executable = destination / "CodexAccountManager.exe"
            uninstaller = destination / "unins000.exe"
            if not executable.is_file() or not uninstaller.is_file():
                raise RuntimeError("Installed application or uninstaller is missing.")
            for link, target in (
                (desktop_link, executable),
                (menu_link, executable),
                (menu_dir / "Uninstall Codex Account Manager.lnk", uninstaller),
            ):
                if not link.is_file():
                    raise RuntimeError(
                        f"Requested shortcut is missing: {link}; "
                        + (Path(temporary) / "install.log").read_text(errors="replace")
                    )
                shortcut = shell.CreateShortcut(str(link))
                if Path(shortcut.TargetPath).resolve() != target.resolve():
                    raise RuntimeError(f"Shortcut points to the wrong executable: {link.name}")
            if startup_command() != f'"{executable}"':
                raise RuntimeError("Start-with-Windows entry is missing or incorrectly quoted.")
            subprocess.run([str(destination / "cli/cx.exe"), "--help"], check=True, timeout=60)
            if sentinel.read_bytes() != expected:
                raise RuntimeError("Installation modified existing user data.")
        finally:
            uninstaller = destination / "unins000.exe"
            if uninstaller.is_file():
                subprocess.run([str(uninstaller), *flags], check=True, timeout=180)
        if (
            (destination / "CodexAccountManager.exe").exists()
            or desktop_link.exists()
            or menu_dir.exists()
            or startup_command() is not None
        ):
            raise RuntimeError(
                "Uninstall left application files, shortcuts or startup entry behind."
            )
        if sentinel.read_bytes() != expected:
            raise RuntimeError("Uninstall modified existing user data.")
    sentinel.unlink()
    data_dir.rmdir()
    print("Installation, CLI, shortcuts, startup entry and user-data preservation verified.")


if __name__ == "__main__":
    main()
