# PyInstaller spec for Codex Account Manager (Windows).
#
# Build:
#   pip install -e ".[gui]" pyinstaller
#   pyinstaller packaging/CodexAccountManager.spec
#
# Produces dist/CodexAccountManager/CodexAccountManager.exe (a windowed, tray app) and
# dist/cx/cx.exe (the console CLI). Bundle dist/CodexAccountManager into the installer
# and/or zip it for the portable release.

# ruff: noqa
import os
import sys
import runpy
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# Keep DLL discovery independent of unrelated tools installed on PATH.
# Qt uses Windows ICU; a same-named third-party ICU can have incompatible exports.
if sys.platform == "win32":
    windows = os.environ.get("SystemRoot", "C:/Windows")
    os.environ["PATH"] = os.pathsep.join([
        os.path.dirname(sys.executable), sys.base_prefix,
        os.path.join(windows, "System32"), windows,
    ])

_root = Path(SPECPATH).parent
_notices = runpy.run_path(str(_root / "scripts/bundle_licenses.py"))["collect_notices"](_root)
_hidden = collect_submodules("codex_account_manager")

_common = dict(
    pathex=["src"],
    hiddenimports=_hidden,
    hookspath=[str(_root / "packaging/hooks")],
    datas=[(str(_notices), "licenses"), (str(_root / "THIRD_PARTY_NOTICES.md"), "licenses"), (str(_root / "LICENSE"), "licenses")],
    runtime_hooks=[],
    excludes=["tkinter", "mypy", "pydantic.mypy", "pytest", "ruff"],
    noarchive=False,
)

# --- GUI (windowed, no console) -------------------------------------------- #
gui_a = Analysis(["../src/codex_account_manager/gui/tray_main.py"], **_common)
gui_a.binaries = [item for item in gui_a.binaries if Path(item[0]).name != "opengl32sw.dll"]
gui_pyz = PYZ(gui_a.pure)
gui_exe = EXE(
    gui_pyz, gui_a.scripts, [], exclude_binaries=True,
    name="CodexAccountManager", console=False, icon=os.path.join(SPECPATH, "assets", "app.ico"),
)
gui_coll = COLLECT(
    gui_exe, gui_a.binaries, gui_a.datas, name="CodexAccountManager",
)

# --- CLI (console) ---------------------------------------------------------- #
cli_a = Analysis(["../src/codex_account_manager/cli/main.py"], **_common)
cli_a.binaries = [item for item in cli_a.binaries if Path(item[0]).name != "opengl32sw.dll"]
cli_pyz = PYZ(cli_a.pure)
cli_exe = EXE(
    cli_pyz, cli_a.scripts, [], exclude_binaries=True,
    name="cx", console=True, icon=os.path.join(SPECPATH, "assets", "app.ico"),
)
cli_coll = COLLECT(
    cli_exe, cli_a.binaries, cli_a.datas, name="cx",
)
