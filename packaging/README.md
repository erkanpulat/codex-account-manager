# Packaging Codex Account Manager for Windows

This produces a Python-free Windows build: a windowed tray app
(`CodexAccountManager.exe`), the console CLI (`cx.exe`), an installer, and a
portable ZIP.

## Prerequisites

- Windows, Python 3.11–3.13
- `pip install -e ".[gui]" pyinstaller`
- [Inno Setup 6](https://jrsoftware.org/isdl.php) for the installer (`iscc` on PATH)

## 1. Build the executables (PyInstaller)

Close any application running from the output directory before rebuilding;
Windows locks its loaded EXE and DLL files. To keep it running, build with
`--distpath build/release-candidate` and pass that EXE path to the smoke check.

```powershell
pyinstaller packaging/CodexAccountManager.spec
```

Output:
- `dist/CodexAccountManager/` — the windowed GUI/tray app
- `dist/cx/` — the console CLI

Smoke-test:

```powershell
dist\cx\cx.exe --help
dist\CodexAccountManager\CodexAccountManager.exe   # should appear in the tray
```

## 2. Build the installer (Inno Setup)

```powershell
iscc packaging/installer.iss
```

For a candidate built outside `dist`, pass its absolute directory with
`iscc /DBundleRoot="C:\path\to\candidate" packaging/installer.iss`.

Output: `installer/Output/CodexAccountManager-Setup-<version>.exe`

- Installs per-user (no admin), into `%LOCALAPPDATA%\Programs\CodexAccountManager`.
- Offers Turkish and English setup text.
- Adds a Start Menu shortcut and an uninstaller; the desktop shortcut is optional.
- Optional "start with Windows" uses the per-user Run registry key (no admin).

## 3. Portable ZIP

```powershell
Compress-Archive -Path dist\CodexAccountManager\* -DestinationPath CodexAccountManager-portable-<version>.zip
```

## 4. GitHub Releases

Upload both artifacts:
- `CodexAccountManager-Setup-<version>.exe`
- `CodexAccountManager-portable-<version>.zip`

> The user's data directory (`%LOCALAPPDATA%\CodexAccountManager`) and the shared
> Codex home (`~/.codex`) are never touched by the installer or uninstaller, so
> existing profiles and history survive upgrades and removal.


The spec limits build-time DLL discovery to Python and Windows directories. This
prevents unrelated tools on PATH from supplying an incompatible `icuuc.dll`.
Qt's imports are satisfied by [Windows ICU](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-).
After changing the build environment, use `python -m PyInstaller --clean --noconfirm packaging/CodexAccountManager.spec`.
Always launch the packaged GUI and verify that its main window opens; a successful
build or CLI help check alone does not validate Qt DLL loading.

Run `python scripts/verify_windows_package.py` after building (close other instances first). It starts the real EXE with temporary data/home directories, requires the main window to open, then terminates only that test process. The same check runs in Windows packaging CI.

## Publication checklist

1. Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md) and inspect `git diff --check`.
2. Run dependency, static security and secret scans as configured in CI. Review filenames and personal information as well as credentials.
3. Commit the intended source. Inspect `git status --short`; never add ignored runtime files with `git add -f`.
4. Push the reviewed branch to the intended GitHub repository. Verify the remote URL with `git remote -v` before pushing.
5. Alternatively use `git archive --format=zip --prefix=codex-account-manager/ --output=dist/codex-account-manager-source.zip HEAD`. Create `dist` first. A Git archive contains the committed source only, without history or ignored files.
6. Wait for the Windows/Linux checks to pass on GitHub. Local checks do not substitute for those platform runs.
7. Build portable Windows packages using this guide, run the real executable smoke check, and attach binaries to a tagged release. Do not mix binaries or local account data into the source tree.

The `.venv`, cache, build and dist directories may be needed locally; their presence in a checkout does not mean Git will publish them. Runtime data is deliberately excluded.

Windows packaging CI compiles the installer and runs
`python scripts/verify_windows_installer.py` on a disposable GitHub-hosted runner.
The check installs to a temporary directory, verifies the requested desktop
and Start menu shortcuts, their targets, the optional Windows startup registry
entry and CLI. It uninstalls, verifies those entries were removed, and checks
that synthetic user data survives. It
refuses to run on a personal machine or a self-hosted runner. A configured CI step
is not evidence that the installer passed; inspect its completed run.

The build collects dependency notices into `_internal/licenses/LICENSES.txt`.
The Qt version is pinned so its reviewed notices match the bundled libraries.
When upgrading Qt, update `packaging/licenses` from the matching upstream source
and review its notices before rebuilding. The build rejects missing Qt notices.
