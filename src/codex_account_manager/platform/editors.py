"""Explicit project navigation to known local Windows editors."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_EDITORS = {
    "VS Code": ("Microsoft VS Code", "Code.exe"),
    "Cursor": ("cursor", "Cursor.exe"),
    "Windsurf": ("Windsurf", "Windsurf.exe"),
}


def vscode_connection_status() -> str:
    """Check local prerequisites without launching editors or enabling extensions.

    Custom extension directories cannot be inferred safely; an undetected
    extension is reported as such, never as proof it is uninstalled or disabled.
    Live owner/turn verification remains mandatory before any continuation.
    """
    executable = installed_editors().get("VS Code")
    if executable is None:
        return "missing_editor"
    roots = [Path.home() / ".vscode" / "extensions", executable.parent / "data/extensions"]
    if directory := os.environ.get("VSCODE_EXTENSIONS"):
        roots.append(Path(directory))
    for root in roots:
        for manifest in root.glob("openai.chatgpt-*/package.json"):
            try:
                if manifest.stat().st_size > 1_048_576:
                    continue
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("publisher", "").lower() == "openai" and data.get("name") == "chatgpt":
                    return "installed"
            except (OSError, ValueError, AttributeError):
                continue
    return "extension_undetected"


def installed_editors() -> dict[str, Path]:
    if sys.platform != "win32":
        return {}
    roots = []
    if local := os.environ.get("LOCALAPPDATA"):
        roots.append(Path(local) / "Programs")
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        if value := os.environ.get(key):
            roots.append(Path(value))
    found = {}
    for name, (folder, executable) in _EDITORS.items():
        for root in roots:
            candidate = root / folder / executable
            if candidate.is_file():
                found[name] = candidate
                break
    return found


def open_project(editor: str, workspace: str) -> None:
    executable = installed_editors().get(editor)
    if executable is None:
        raise ValueError("The selected editor is not installed in a supported location.")
    if not workspace or workspace.startswith(("\\", "//")):
        raise ValueError("Choose an existing local project folder.")
    directory = Path(workspace)
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("Choose an existing local project folder.")
    env = os.environ.copy()
    env.pop("ELECTRON_RUN_AS_NODE", None)
    subprocess.Popen(
        [str(executable), "--new-window", str(directory.resolve())],
        shell=False,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
