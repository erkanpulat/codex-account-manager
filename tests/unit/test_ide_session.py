from unittest.mock import Mock

import pytest

from codex_account_manager.core.errors import AppServerError
from codex_account_manager.platform import ide_session as module


async def test_refresh_closes_once_reopens_exact_thread_and_reuses_account(tmp_path, monkeypatch):
    before = module.EditorWindow(tmp_path / "Code.exe", 1, 10, 100)
    after = module.EditorWindow(before.executable, 2, 20, 200)
    current = [before]
    monkeypatch.setattr(module, "running_window", lambda: current[0])
    closed = Mock()
    monkeypatch.setattr(module, "request_close", closed)
    monkeypatch.setattr(module, "has_exited", lambda _: True)
    opened = []

    def reopen(executable, thread_id, workspace=None):
        opened.append((executable, thread_id, workspace))
        current[0] = after

    monkeypatch.setattr(module, "open_thread", reopen)
    session = module.IDESession()
    assert await session.needs_refresh("target")
    await session.refresh("target", "thread", str(tmp_path))
    assert not await session.needs_refresh("target")
    await session.refresh("target", "second", str(tmp_path))
    closed.assert_called_once_with(before)
    assert opened == [
        (before.executable, "thread", str(tmp_path)),
        (before.executable, "second", None),
    ]
    assert await session.needs_refresh("different")


async def test_save_dialog_timeout_never_forces_exit_or_launch(tmp_path, monkeypatch):
    import asyncio

    window = module.EditorWindow(tmp_path / "Code.exe", 1, 10, 100)
    monkeypatch.setattr(module, "running_window", lambda: window)
    close = Mock()
    launch = Mock()
    monkeypatch.setattr(module, "request_close", close)
    monkeypatch.setattr(module, "open_thread", launch)
    monkeypatch.setattr(module, "has_exited", lambda _: False)
    original = asyncio.timeout
    monkeypatch.setattr(module.asyncio, "timeout", lambda _: original(0.01))
    with pytest.raises(AppServerError, match="save dialog"):
        await module.IDESession().refresh("target", "thread", str(tmp_path))
    close.assert_called_once()
    launch.assert_not_called()


@pytest.mark.parametrize("workspace", ["relative", "//remote/share", "missing"])
async def test_invalid_workspace_does_not_close_window(tmp_path, monkeypatch, workspace):
    monkeypatch.setattr(
        module, "running_window", lambda: module.EditorWindow(tmp_path / "Code.exe", 1, 10, 100)
    )
    close = Mock()
    monkeypatch.setattr(module, "request_close", close)
    with pytest.raises(AppServerError, match="local workspace"):
        await module.IDESession().refresh("target", "thread", workspace)
    close.assert_not_called()


def test_open_thread_uses_literal_workspace_and_existing_extension_route(tmp_path, monkeypatch):
    launch = Mock()
    monkeypatch.setattr(module, "launch_from_explorer", launch)
    executable = tmp_path / "Code.exe"
    module.open_thread(executable, "thread-id", str(tmp_path))
    assert launch.call_args_list[0].args == (
        executable,
        ["--reuse-window", str(tmp_path.resolve())],
    )
    assert launch.call_args_list[1].args == (
        executable,
        ["--reuse-window", "--open-url", "vscode://openai.chatgpt/local/thread-id"],
    )
    launch.reset_mock()
    with pytest.raises(AppServerError):
        module.open_thread(executable, "../unrelated")
    launch.assert_not_called()
