"""Explicit, per-user setup using OpenAI's Windows standalone installer."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from codex_account_manager.codex.runtime import codex_command, find_codex
from codex_account_manager.core.errors import CodexNotFoundError
from codex_account_manager.core.operation_lock import OperationLock
from codex_account_manager.core.paths import paths

INSTALL_URL = "https://chatgpt.com/codex/install.ps1"
DOCS_URL = "https://learn.chatgpt.com/docs/codex/cli"


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("The official CLI installer could not be verified.")


def cli_version() -> str | None:
    try:
        executable = find_codex()
    except CodexNotFoundError:
        return None
    try:
        result = subprocess.run(
            codex_command("--version", executable=executable),
            capture_output=True,
            timeout=15,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        match = re.fullmatch(
            rb"codex-cli ([0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?)\s*", result.stdout
        )
        if match:
            return match[1].decode("ascii")
    except (OSError, subprocess.SubprocessError):
        pass
    raise RuntimeError("Codex CLI was found but could not be started. Check your installation.")


def install_cli() -> str:
    if sys.platform != "win32":
        raise RuntimeError("Automatic CLI installation requires Windows.")
    with OperationLock(paths.data_dir / "cli-install.lock"):
        existing = cli_version()
        if existing:
            return existing
        request = urllib.request.Request(INSTALL_URL, headers={"User-Agent": "QuotaCrew"})
        try:
            with urllib.request.build_opener(_NoRedirects()).open(request, timeout=30) as response:
                if response.url != INSTALL_URL:
                    raise RuntimeError("The official CLI installer could not be verified.")
                script = response.read(1024 * 1024 + 1)
            if not script or len(script) > 1024 * 1024:
                raise RuntimeError("The official CLI installer could not be verified.")
            script.decode("utf-8-sig")
            powershell = (
                Path(os.environ.get("SystemRoot", "C:/Windows"))
                / "System32/WindowsPowerShell/v1.0/powershell.exe"
            )
            environment = os.environ.copy()
            for key in list(environment):
                if key.upper().startswith("CODEX_INSTALL") or key.upper() in {
                    "CODEX_RELEASE",
                    "CODEX_HOME",
                }:
                    environment.pop(key)
            environment["CODEX_NON_INTERACTIVE"] = "1"
            with tempfile.TemporaryDirectory(prefix="codex-cli-setup-") as temporary:
                installer = Path(temporary) / "install.ps1"
                installer.write_bytes(script)
                subprocess.run(
                    [
                        str(powershell),
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(installer),
                    ],
                    env=environment,
                    capture_output=True,
                    timeout=600,
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise RuntimeError(
                "Codex CLI installation did not finish. Retry or use the official installation guide."
            ) from exc
        version = cli_version()
        if not version:
            raise RuntimeError(
                "Codex CLI installation could not be confirmed. Open the official guide."
            )
        return version
