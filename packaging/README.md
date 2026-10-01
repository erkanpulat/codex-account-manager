# Packaging QuotaCrew for Windows

Build self-contained Windows packages from the reviewed QuotaCrew source:
the desktop app (`QuotaCrew.exe`), console CLI (`cx.exe`), installer and portable ZIP.
Python is bundled; users do not need to install it separately.

Fresh installations use `%LOCALAPPDATA%\Programs\QuotaCrew`. The installer and
uninstaller preserve application data and the shared Codex conversation history.
Publish packages from `erkanpulat/codex-quotacrew`, the trusted repository used by
the in-app updater.

Windows installer and portable packages include the concise bilingual
`WINDOWS-README.md` as `README.md`. It links to the illustrated online guides,
downloads and security policy, so the binary package has no missing local images
or documentation links. Source distributions retain the full repository READMEs.

## Publishing updates

1. Set the same new `x.y.z` version in `pyproject.toml`, `src/codex_account_manager/__init__.py` and `packaging/installer.iss`. Add the changelog and complete the checks.
2. Commit and push the reviewed source when ready to publish. Local working-tree changes are not release inputs.
3. Run **Actions → Publish release → Run workflow** from the intended branch, entering that exact version. The workflow checks versions, runs tests and builds the Windows installer. It creates a draft, uploads the installer and checksums, verifies GitHub's asset digest, then publishes it as the latest stable release. A failed build does not publish; an upload failure leaves a draft for review.
4. Installed clients detect a higher version on their next daily check, or immediately via **Check for updates**. This is polling, not a push notification service. Drafts and prereleases are excluded. Replacing an asset under the same version does not update already-installed clients; issue a new patch version.

The updater trusts the fixed repository's HTTPS release metadata and GitHub's
SHA-256 asset digest. A missing digest disables installation. This is integrity
verification, not publisher code signing; protect the GitHub repository and
release credentials. The installer waits for QuotaCrew to exit and does
not force-close Codex, VS Code or other programs. Account data lives outside the
installation directory. Only the app-owned `_internal` and `cli/_internal`
dependency directories are replaced during installation; do not store user
files in them. Failed installations can be rerun from the release page.

## Prerequisites

- Windows, Python 3.11–3.13
- `pip install -e ".[gui]" pyinstaller`
- [Inno Setup 6](https://jrsoftware.org/isdl.php) for the installer (`iscc` on PATH)

## 1. Build the executables (PyInstaller)

Close any application running from the output directory before rebuilding;
Windows locks its loaded EXE and DLL files. To keep it running, build with
`--distpath build/release-candidate` and pass that EXE path to the smoke check.

```powershell
pyinstaller packaging/QuotaCrew.spec
```

Output:
- `dist/QuotaCrew/` — the windowed GUI/tray app
- `dist/cx/` — the console CLI

Smoke-test:

```powershell
dist\cx\cx.exe --help
dist\QuotaCrew\QuotaCrew.exe   # should appear in the tray
```

## 2. Build the installer (Inno Setup)

```powershell
iscc packaging/installer.iss
```

For a candidate built outside `dist`, pass its absolute directory with
`iscc /DBundleRoot="C:\path\to\candidate" packaging/installer.iss`.

Output: `installer/Output/QuotaCrew-Setup-<version>.exe`

- Installs per-user (no admin), into `%LOCALAPPDATA%\Programs\QuotaCrew`.
- Offers Turkish and English setup text.
- Adds a Start Menu shortcut and an uninstaller; the desktop shortcut is optional.
- Optional "start with Windows" uses the per-user Run registry key (no admin).

## 3. Portable ZIP

```powershell
Copy-Item packaging\WINDOWS-README.md -Destination dist\QuotaCrew\README.md
Copy-Item LICENSE,THIRD_PARTY_NOTICES.md -Destination dist\QuotaCrew
Compress-Archive -Path dist\QuotaCrew\* -DestinationPath QuotaCrew-portable-<version>.zip
```

## 4. GitHub Releases

Upload both artifacts:
- `QuotaCrew-Setup-<version>.exe`
- `QuotaCrew-portable-<version>.zip`

> The user's data directory (`%LOCALAPPDATA%\CodexAccountManager`) and the shared
> Codex home (`~/.codex`) are never touched by the installer or uninstaller, so
> existing profiles and history survive upgrades and removal.


The spec limits build-time DLL discovery to Python and Windows directories. This
prevents unrelated tools on PATH from supplying an incompatible `icuuc.dll`.
Qt's imports are satisfied by [Windows ICU](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-).
After changing the build environment, use `python -m PyInstaller --clean --noconfirm packaging/QuotaCrew.spec`.
Always launch the packaged GUI and verify that its main window opens; a successful
build or CLI help check alone does not validate Qt DLL loading.

Run `python scripts/verify_windows_package.py` after building (close other instances first). It starts the real EXE with temporary data/home directories, requires the main window to open, then terminates only that test process. The same check runs in Windows packaging CI.

## Publication checklist

1. Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md) and inspect `git diff --check`.
2. Run dependency, static security and secret scans as configured in CI. Review filenames and personal information as well as credentials.
3. Commit the intended source. Inspect `git status --short`; never add ignored runtime files with `git add -f`.
4. Push the reviewed branch to the intended GitHub repository. Verify the remote URL with `git remote -v` before pushing.
5. Alternatively use `git archive --format=zip --prefix=codex-quotacrew/ --output=dist/codex-quotacrew-source.zip HEAD`. Create `dist` first. A Git archive contains the committed source only, without history or ignored files.
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
