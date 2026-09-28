import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell compatibility")
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.ps1"


def run_windows_powershell(command, script):
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return subprocess.run(
        [
            str(executable),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        env={**os.environ, "TEST_BOOTSTRAP_SCRIPT": str(script), "TEST_PYTHON": sys.executable},
        capture_output=True,
        text=True,
        # Parsing/interpreter selection is independent of cold PowerShell startup.
        timeout=60,
    )


def test_bootstrap_parses_in_windows_powershell_51():
    result = run_windows_powershell(
        "$errors = $null; $tokens = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        "$env:TEST_BOOTSTRAP_SCRIPT, [ref]$tokens, [ref]$errors); "
        "if ($errors.Count) { $errors | Out-String | Write-Output; exit 1 }",
        SCRIPT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bootstrap_tries_next_interpreter_after_launcher_stderr(tmp_path):
    project = tmp_path / "bootstrap test"
    project.mkdir()
    script = project / "bootstrap.ps1"
    script.write_bytes(SCRIPT.read_bytes())
    result = run_windows_powershell(
        r"""function py {
            if ($args[0] -eq "-3.13") {
                & $env:TEST_PYTHON -c "import sys; sys.stderr.write('Interpreter unavailable'); sys.exit(103)"
                return
            }
            if ($args[0] -ne "-3.12") { throw "Unexpected interpreter choice" }
            if ($args[1] -eq "-c") {
                & $env:TEST_PYTHON -c "pass"
                return
            }
            if ($args[1] -eq "-m" -and $args[2] -eq "venv") {
                throw "SUPPORTED_INTERPRETER_SELECTED"
            }
            throw "Unexpected launcher invocation"
        }
        try {
            & $env:TEST_BOOTSTRAP_SCRIPT
            exit 2
        } catch {
            if ($_.Exception.Message -ne "SUPPORTED_INTERPRETER_SELECTED") {
                Write-Output $_.Exception.Message
                exit 1
            }
            exit 0
        }""",
        script,
    )
    assert result.returncode == 0, result.stdout + result.stderr
