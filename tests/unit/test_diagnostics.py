import asyncio
from unittest.mock import AsyncMock

import pytest

from codex_account_manager.diagnostics.doctor import _codex_version


class Process:
    def __init__(self, code=0, stdout=b"codex-cli 1.0", stderr=b""):
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr
        self.killed = False

    async def communicate(self):
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True
        self.returncode = -1

    async def wait(self):
        return self.returncode


async def test_version_uses_resolved_executable_and_detaches_stdin(monkeypatch):
    launch = AsyncMock(return_value=Process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    assert await _codex_version("C:/tool/codex.exe") == "codex-cli 1.0"
    assert launch.call_args.args == ("C:/tool/codex.exe", "--version")
    assert launch.call_args.kwargs["stdin"] == asyncio.subprocess.DEVNULL


@pytest.mark.parametrize(
    "process, expected",
    [
        (Process(9, b"not a version", b"failed password=private-value"), "code 9"),
        (Process(stdout=b""), "no version"),
    ],
)
async def test_version_reports_failed_exit_and_empty_output(monkeypatch, process, expected):
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(ValueError, match=expected) as caught:
        await _codex_version("codex.exe")
    assert "private-value" not in str(caught.value)


async def test_version_timeout_kills_subprocess(monkeypatch):
    process = Process(code=None)
    launch = AsyncMock(return_value=process)

    async def timeout(coro, **_kwargs):
        coro.close()
        raise TimeoutError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(asyncio, "wait_for", timeout)
    with pytest.raises(TimeoutError, match="15 seconds"):
        await _codex_version("codex.exe")
    assert process.killed


async def test_export_excludes_aliases_paths_raw_errors_and_logs(tmp_paths, tmp_path, monkeypatch):
    import json
    import zipfile

    from codex_account_manager.diagnostics import bundle
    from codex_account_manager.diagnostics.doctor import CheckResult

    private = "private@example.invalid"
    checks = [
        CheckResult(f"profile:{private}", True, "auth=yes, bound=yes"),
        CheckResult("database", True, str(tmp_path / "personal" / "accounts.db")),
        CheckResult("profiles", False, f"Unexpected upstream output: {private}"),
        CheckResult(private, False, private),
        CheckResult("codex_version", True, "codex-cli 0.157.0"),
        CheckResult("profile_count", True, "1"),
    ]
    monkeypatch.setattr(bundle, "run_diagnostics", AsyncMock(return_value=checks))
    tmp_paths.logs_dir.mkdir(parents=True, exist_ok=True)
    (tmp_paths.logs_dir / "account-manager.log").write_text(private)
    target = await bundle.export_bundle(tmp_path / "report.zip")
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {"diagnostics.json", "environment.json"}
        content = "".join(archive.read(name).decode() for name in archive.namelist())
        assert private not in content
        assert str(tmp_path) not in content
        rows = json.loads(archive.read("diagnostics.json"))
    assert rows[0] == {"name": "profile:1", "ok": True, "detail": "ready"}
    assert rows[2]["detail"] == "needs_attention"
    assert rows[3]["detail"] == "codex-cli 0.157.0"
    assert rows[4]["detail"] == "1"


async def test_export_does_not_trust_version_output(tmp_path, monkeypatch):
    import zipfile

    from codex_account_manager.diagnostics import bundle
    from codex_account_manager.diagnostics.doctor import CheckResult

    monkeypatch.setattr(
        bundle,
        "run_diagnostics",
        AsyncMock(
            return_value=[
                CheckResult("codex_version", False, "codex-cli 0.157.0 private-information"),
            ]
        ),
    )
    with zipfile.ZipFile(await bundle.export_bundle(tmp_path / "report.zip")) as archive:
        assert b"private-information" not in archive.read("diagnostics.json")
