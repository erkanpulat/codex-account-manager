import io
import subprocess
from unittest.mock import Mock

import pytest

from codex_account_manager.codex import runtime, setup
from codex_account_manager.core.errors import CodexNotFoundError


def test_detection_checks_version_without_starting_a_task(monkeypatch):
    monkeypatch.setattr(setup, "find_codex", lambda: "codex.exe")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b"codex-cli 0.143.0\n"))
    monkeypatch.setattr(setup.subprocess, "run", run)
    assert setup.cli_version() == "0.143.0"
    assert run.call_args.args[0] == ["codex.exe", "--version"]
    run.return_value.stdout = b"unexpected private output"
    with pytest.raises(RuntimeError, match="could not be started"):
        setup.cli_version()


def test_missing_cli_is_distinct_from_broken_cli(monkeypatch):
    monkeypatch.setattr(setup, "find_codex", Mock(side_effect=CodexNotFoundError("missing")))
    assert setup.cli_version() is None


@pytest.mark.parametrize("url", ["file:///private", "http://chatgpt.com", "https://example.com"])
def test_official_installer_rejects_redirects(url):
    with pytest.raises(RuntimeError, match="could not be verified"):
        setup._NoRedirects().redirect_request(None, None, 302, "", {}, url)


def test_standalone_cli_is_found_without_restarting_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda _: None)
    if runtime.os.name != "nt":
        pytest.skip("Windows standalone location")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    binary = tmp_path / "Programs/OpenAI/Codex/bin/codex.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic")
    assert runtime.find_codex() == str(binary)


@pytest.mark.parametrize("existing", [True, False])
def test_install_only_when_missing_and_verifies_result(tmp_paths, monkeypatch, existing):
    if setup.sys.platform != "win32":
        pytest.skip("Windows installer")
    version = Mock(side_effect=["0.143.0"] if existing else [None, "0.143.0"])
    monkeypatch.setattr(setup, "cli_version", version)
    response = io.BytesIO(b"Write-Output 'synthetic installer'")
    response.url = setup.INSTALL_URL
    network = Mock(return_value=response)
    monkeypatch.setattr(setup.urllib.request, "build_opener", lambda *_: Mock(open=network))
    run = Mock()
    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setenv("CODEX_INSTALL_DIR", "unrelated")
    monkeypatch.setenv("CODEX_HOME", "unrelated-profile")
    assert setup.install_cli() == "0.143.0"
    if existing:
        network.assert_not_called()
        run.assert_not_called()
    else:
        arguments = run.call_args.args[0]
        assert "-File" in arguments and "-NonInteractive" in arguments
        env = run.call_args.kwargs["env"]
        assert env["CODEX_NON_INTERACTIVE"] == "1"
        assert "CODEX_INSTALL_DIR" not in env
        assert "CODEX_HOME" not in env
        assert not __import__("pathlib").Path(arguments[-1]).exists()
        assert version.call_count == 2
